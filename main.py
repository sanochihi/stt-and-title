from __future__ import annotations

import logging
import time

from src.bedrock_service import BedrockService
from src.config import load_settings
from src.db_service import TalksRepository
from src.logging_config import setup_logging
from src.pipeline import ProcessingPipeline
from src.s3_service import S3Service
from src.transcribe_service import TranscribeService


def main() -> None:
    settings = load_settings()
    logger = setup_logging(settings.log_file)
    logger.info("STT アプリを起動しました")

    s3 = S3Service(settings)
    transcribe = TranscribeService(settings, s3)
    bedrock = BedrockService(settings)
    talks_repo = TalksRepository(settings)
    pipeline = ProcessingPipeline(settings, s3, transcribe, bedrock, talks_repo)

    try:
        while True:
            try:
                pipeline.poll_and_process()
            except Exception:
                logging.getLogger("stt_app").exception("ポーリング中にエラーが発生しました")
            time.sleep(settings.poll_interval_seconds)
    except KeyboardInterrupt:
        logger.info("中断シグナルを受信しました")
    finally:
        pipeline.shutdown(wait=True)


if __name__ == "__main__":
    main()
