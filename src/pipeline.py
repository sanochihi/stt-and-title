from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath

from src.bedrock_service import BedrockService
from src.config import Settings
from src.db_service import TalksRepository
from src.filename import (
    parse_audio_filename,
    summary_key_for_transcript,
    transcript_key_for_webm,
)
from src.s3_service import S3Service
from src.transcribe_service import TranscribeService

logger = logging.getLogger("stt_app.pipeline")


class ProcessingPipeline:
    def __init__(
        self,
        settings: Settings,
        s3: S3Service,
        transcribe: TranscribeService,
        bedrock: BedrockService,
        talks_repo: TalksRepository,
    ) -> None:
        self._settings = settings
        self._s3 = s3
        self._transcribe = transcribe
        self._bedrock = bedrock
        self._talks_repo = talks_repo

        self._claim_lock = threading.Lock()
        self._in_flight_lock = threading.Lock()
        self._in_flight: set[str] = set()

        self._transcribe_sem = threading.Semaphore(settings.max_concurrent_transcribe)
        self._bedrock_sem = threading.Semaphore(settings.max_concurrent_bedrock)
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_worker_threads,
            thread_name_prefix="stt-worker",
        )

        logger.info(
            "並列パイプライン: transcribe=%d bedrock=%d workers=%d",
            settings.max_concurrent_transcribe,
            settings.max_concurrent_bedrock,
            settings.max_worker_threads,
        )

    def shutdown(self, wait: bool = True) -> None:
        logger.info("並列パイプラインを停止します (wait=%s)", wait)
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _process_after_claim(self, processing_audio_key: str) -> None:
        processing_prefix = self._settings.s3_processing_prefix
        meta = parse_audio_filename(processing_audio_key)

        with self._transcribe_sem:
            logger.info("Transcribe 開始: %s", meta.basename)
            whole_text = self._transcribe.transcribe_webm_to_text(processing_audio_key)
            logger.info("Transcribe 終了: %s", meta.basename)

        transcript_key = transcript_key_for_webm(processing_prefix, meta.basename)
        self._s3.put_text(transcript_key, whole_text)

        with self._bedrock_sem:
            logger.info("Bedrock 要約開始: %s", meta.basename)
            summary = self._bedrock.summarize(whole_text)
            logger.info("Bedrock 要約終了: %s", meta.basename)

        transcript_basename = PurePosixPath(transcript_key).name
        summary_key = summary_key_for_transcript(processing_prefix, transcript_basename)
        self._s3.put_text(summary_key, summary)

        self._talks_repo.update_talk(
            game_id=meta.game_id,
            topic_number=meta.topic_number,
            whole_text=whole_text,
            summary=summary,
        )

        self._s3.move_to_processed(
            [processing_audio_key, transcript_key, summary_key]
        )
        logger.info("処理完了: %s", meta.basename)

    def _worker(self, audio_key: str) -> None:
        try:
            meta = parse_audio_filename(audio_key)
            processing_prefix = self._settings.s3_processing_prefix
            processing_audio_key = f"{processing_prefix}{meta.basename}"

            with self._claim_lock:
                claimed = self._s3.try_claim_audio_to_processing(
                    audio_key, processing_audio_key
                )
            if not claimed:
                return

            logger.info("処理開始 (claim 済): %s", audio_key)
            self._process_after_claim(processing_audio_key)
        except Exception:
            logger.exception("ファイル処理に失敗しました: %s", audio_key)
        finally:
            with self._in_flight_lock:
                self._in_flight.discard(audio_key)

    def poll_and_process(self) -> None:
        keys = self._s3.list_pending_webm_keys()
        submitted = 0
        for key in keys:
            with self._in_flight_lock:
                if key in self._in_flight:
                    continue
                self._in_flight.add(key)
            self._executor.submit(self._worker, key)
            submitted += 1
        if submitted:
            with self._in_flight_lock:
                in_flight_count = len(self._in_flight)
            logger.info(
                "ポーリング: 新規投入=%d 件 処理中(含む待ち)=%d 件",
                submitted,
                in_flight_count,
            )
