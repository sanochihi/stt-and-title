from __future__ import annotations

import logging
from typing import Iterator

import boto3
from botocore.exceptions import ClientError

from src.config import Settings

logger = logging.getLogger("stt_app.s3")


class S3Service:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = boto3.client("s3", region_name=settings.aws_region)
        self._bucket = settings.s3_bucket_name

    def list_pending_webm_keys(self) -> list[str]:
        prefix = self._settings.s3_audio_prefix
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith(".webm") and not key.endswith("/"):
                    keys.append(key)
        keys.sort()
        logger.info("S3 ポーリング: prefix=%s webm=%d 件", prefix, len(keys))
        return keys

    def move_object(self, source_key: str, dest_key: str) -> None:
        logger.info("S3 移動: s3://%s/%s -> s3://%s/%s", self._bucket, source_key, self._bucket, dest_key)
        self._client.copy_object(
            Bucket=self._bucket,
            CopySource={"Bucket": self._bucket, "Key": source_key},
            Key=dest_key,
        )
        self._client.delete_object(Bucket=self._bucket, Key=source_key)

    def try_claim_audio_to_processing(self, audio_key: str, processing_audio_key: str) -> bool:
        """
        audio prefix から processing へ移動して処理権を取得する。
        既に他ワーカーが取得済みの場合は False（exactly-once の claim 用）。
        """
        if not self.object_exists(audio_key):
            logger.info("claim スキップ (audio に存在しない): %s", audio_key)
            return False
        if self.object_exists(processing_audio_key):
            logger.info(
                "claim スキップ (processing に同名ファイルあり): %s",
                processing_audio_key,
            )
            return False
        try:
            self.move_object(audio_key, processing_audio_key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                logger.info("claim 失敗 (競合の可能性): %s", audio_key)
                return False
            raise
        logger.info("claim 成功: %s -> %s", audio_key, processing_audio_key)
        return True

    def put_text(self, key: str, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        logger.info("S3 テキスト保存: s3://%s/%s (%d 文字)", self._bucket, key, len(body))
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType=content_type,
        )

    def get_text(self, key: str) -> str:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read().decode("utf-8")

    def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def media_uri(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    def move_to_processed(self, keys: Iterator[str]) -> None:
        processed_prefix = self._settings.s3_processed_prefix
        for key in keys:
            basename = key.split("/")[-1]
            dest_key = f"{processed_prefix}{basename}"
            self.move_object(key, dest_key)

    def list_object_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                keys.append(key)
        keys.sort()
        return keys

    def delete_object(self, key: str) -> None:
        logger.info("S3 削除: s3://%s/%s", self._bucket, key)
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def rollback_prefix(self, source_prefix: str) -> tuple[int, int]:
        """
        指定 prefix 内の .txt を削除し、それ以外のファイルを audio prefix へ移動する。
        Returns: (削除したテキスト件数, 移動した音声件数)
        """
        audio_prefix = self._settings.s3_audio_prefix
        deleted = 0
        moved = 0
        keys = self.list_object_keys(source_prefix)
        logger.info(
            "ロールバック開始: source=s3://%s/%s 対象=%d 件",
            self._bucket,
            source_prefix,
            len(keys),
        )
        for key in keys:
            basename = key.split("/")[-1]
            if basename.lower().endswith(".txt"):
                self.delete_object(key)
                deleted += 1
            else:
                dest_key = f"{audio_prefix}{basename}"
                self.move_object(key, dest_key)
                moved += 1
        logger.info(
            "ロールバック完了: source=s3://%s/%s テキスト削除=%d 音声移動=%d",
            self._bucket,
            source_prefix,
            deleted,
            moved,
        )
        return deleted, moved
