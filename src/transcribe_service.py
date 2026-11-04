from __future__ import annotations

import logging
import re
import time
import uuid

import boto3
from botocore.exceptions import ClientError

from src.config import Settings
from src.s3_service import S3Service

logger = logging.getLogger("stt_app.transcribe")


class TranscribeService:
    def __init__(self, settings: Settings, s3: S3Service) -> None:
        self._settings = settings
        self._s3 = s3
        self._client = boto3.client("transcribe", region_name=settings.aws_region)

    def transcribe_webm_to_text(self, s3_key: str) -> str:
        job_name = self._make_job_name(s3_key)
        media_uri = self._s3.media_uri(s3_key)
        logger.info("Transcribe ジョブ開始: job=%s media=%s", job_name, media_uri)

        try:
            self._client.start_transcription_job(
                TranscriptionJobName=job_name,
                Media={"MediaFileUri": media_uri},
                MediaFormat="webm",
                LanguageCode=self._settings.transcribe_language_code,
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConflictException":
                logger.warning("同名ジョブが存在するため待機します: %s", job_name)
            else:
                raise

        self._wait_for_job(job_name)
        transcript_uri = self._get_transcript_uri(job_name)
        transcript_text = self._fetch_transcript_text(transcript_uri)
        logger.info("Transcribe 完了: job=%s 文字数=%d", job_name, len(transcript_text))
        return transcript_text

    def _make_job_name(self, s3_key: str) -> str:
        base = re.sub(r"[^0-9A-Za-z._-]", "-", s3_key.split("/")[-1])
        suffix = uuid.uuid4().hex[:8]
        name = f"stt-{base}-{suffix}"
        return name[:200]

    def _wait_for_job(self, job_name: str, timeout_seconds: int = 3600) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            response = self._client.get_transcription_job(TranscriptionJobName=job_name)
            status = response["TranscriptionJob"]["TranscriptionJobStatus"]
            if status == "COMPLETED":
                return
            if status == "FAILED":
                reason = response["TranscriptionJob"].get("FailureReason", "unknown")
                raise RuntimeError(f"Transcribe ジョブ失敗: {job_name} ({reason})")
            time.sleep(5)
        raise TimeoutError(f"Transcribe ジョブがタイムアウトしました: {job_name}")

    def _get_transcript_uri(self, job_name: str) -> str:
        response = self._client.get_transcription_job(TranscriptionJobName=job_name)
        return response["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]

    def _fetch_transcript_text(self, transcript_uri: str) -> str:
        import json
        import urllib.request

        with urllib.request.urlopen(transcript_uri) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        transcripts = payload.get("results", {}).get("transcripts", [])
        if not transcripts:
            return ""
        return transcripts[0].get("transcript", "").strip()
