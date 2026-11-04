from __future__ import annotations

import argparse
import logging
import sys

from src.config import load_settings
from src.logging_config import setup_logging
from src.s3_service import S3Service


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="S3 の processing / processed をテスト用に audio へ戻す"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--processing",
        action="store_true",
        help=f"{{S3_PROCESSING_PREFIX}} 内を整理（.txt 削除、音声を audio へ移動）",
    )
    group.add_argument(
        "--processed",
        action="store_true",
        help=f"{{S3_PROCESSED_PREFIX}} 内を整理（.txt 削除、音声を audio へ移動）",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="--processing と --processed の両方を実行",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    settings = load_settings()
    setup_logging(settings.log_file)
    logger = logging.getLogger("stt_app.rollback")
    s3 = S3Service(settings)

    targets: list[tuple[str, str]] = []
    if args.processing or args.all:
        targets.append(("processing", settings.s3_processing_prefix))
    if args.processed or args.all:
        targets.append(("processed", settings.s3_processed_prefix))

    total_deleted = 0
    total_moved = 0
    for label, prefix in targets:
        logger.info("rollback_s3: %s (--%s)", label, label)
        deleted, moved = s3.rollback_prefix(prefix)
        total_deleted += deleted
        total_moved += moved

    logger.info(
        "rollback_s3 完了: テキスト削除合計=%d 音声移動合計=%d",
        total_deleted,
        total_moved,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
