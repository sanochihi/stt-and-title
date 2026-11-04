from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    db_user: str
    db_password: str
    db_host: str
    db_port: int
    db_name: str
    db_schema: str

    aws_region: str
    s3_bucket_name: str
    s3_audio_prefix: str
    s3_processing_prefix: str
    s3_processed_prefix: str

    transcribe_language_code: str
    bedrock_model_id: str
    poll_interval_seconds: int
    log_file: str
    max_concurrent_transcribe: int
    max_concurrent_bedrock: int
    max_worker_threads: int


def _require(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"環境変数 {name} が設定されていません (.env を確認してください)")
    return value.strip()


def _optional(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def load_settings(env_path: str | None = None) -> Settings:
    load_dotenv(env_path)

    return Settings(
        db_user=_require("DB_USER"),
        db_password=_require("DB_PASSWORD"),
        db_host=_require("DB_HOST"),
        db_port=int(_require("DB_PORT")),
        db_name=_require("DB_NAME"),
        db_schema=_optional("DB_SCHEMA", "game"),
        aws_region=_require("AWS_REGION"),
        s3_bucket_name=_require("S3_BUCKET_NAME"),
        s3_audio_prefix=_normalize_prefix(_require("S3_AUDIO_PREFIX")),
        s3_processing_prefix=_normalize_prefix(_require("S3_PROCESSING_PREFIX")),
        s3_processed_prefix=_normalize_prefix(_require("S3_PROCESSED_PREFIX")),
        transcribe_language_code=_optional("TRANSCRIBE_LANGUAGE_CODE", "ja-JP"),
        bedrock_model_id=_optional(
            "BEDROCK_MODEL_ID",
            # Claude 3 Haiku はリージョンによって EOL のため Haiku 4.5 の inference profile を既定にする
            "jp.anthropic.claude-haiku-4-5-20251001-v1:0",
        ),
        poll_interval_seconds=int(_optional("POLL_INTERVAL_SECONDS", "10")),
        log_file=_optional("LOG_FILE", "app.log"),
        max_concurrent_transcribe=int(_optional("MAX_CONCURRENT_TRANSCRIBE", "3")),
        max_concurrent_bedrock=int(_optional("MAX_CONCURRENT_BEDROCK", "5")),
        max_worker_threads=int(_optional("MAX_WORKER_THREADS", "8")),
    )


def _normalize_prefix(prefix: str) -> str:
    if prefix and not prefix.endswith("/"):
        return prefix + "/"
    return prefix
