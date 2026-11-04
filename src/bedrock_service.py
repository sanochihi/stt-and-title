from __future__ import annotations

import json
import logging

import boto3
from botocore.exceptions import ClientError

from src.config import Settings

logger = logging.getLogger("stt_app.bedrock")


class BedrockService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def summarize(self, whole_text: str) -> str:
        if not whole_text.strip():
            logger.warning("要約対象テキストが空です")
            return ""

        prompt = (
            "以下の文のこの内容を、「○○の話」や「○○の件」というような短いタイトルにまとめてください。前後の余計な説明は削除し、最終的なタイトルをひとつだけ返してください。\n\n"
            f"{whole_text}"
        )
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        logger.info(
            "Bedrock 要約リクエスト: model=%s 入力文字数=%d",
            self._settings.bedrock_model_id,
            len(whole_text),
        )
        try:
            response = self._client.invoke_model(
                modelId=self._settings.bedrock_model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            message = exc.response.get("Error", {}).get("Message", str(exc))
            logger.error(
                "Bedrock invoke_model 失敗: model=%s code=%s message=%s",
                self._settings.bedrock_model_id,
                code,
                message,
            )
            if code == "ResourceNotFoundException" and "end of its life" in message.lower():
                logger.error(
                    "BEDROCK_MODEL_ID を現行の Haiku inference profile に変更してください "
                    "(例: ap-northeast-1 なら jp.anthropic.claude-haiku-4-5-20251001-v1:0)"
                )
            raise
        result = json.loads(response["body"].read())
        content_blocks = result.get("content", [])
        summary_parts = [block.get("text", "") for block in content_blocks if block.get("type") == "text"]
        summary = "\n".join(part for part in summary_parts if part).strip()
        logger.info("Bedrock 要約完了: 出力文字数=%d", len(summary))
        return summary
