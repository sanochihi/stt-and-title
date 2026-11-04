from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class AudioMetadata:
    game_id: str
    topic_number: int
    basename: str


def parse_audio_filename(s3_key: str) -> AudioMetadata:
    """
    例: 9994699a_5_A_aruaru_0006e4ca_あいう〜_20261029_115102.webm
    -> game_id=9994699a, topic_number=5
    """
    basename = PurePosixPath(s3_key).name
    if not basename.lower().endswith(".webm"):
        raise ValueError(f"webm 以外のファイルです: {basename}")

    stem = basename[: -len(".webm")]
    parts = stem.split("_")
    if len(parts) < 2:
        raise ValueError(f"ファイル名から game_id / 通番を取得できません: {basename}")

    game_id = parts[0]
    if not re.fullmatch(r"[A-Za-z0-9]+", game_id):
        raise ValueError(f"game_id の形式が不正です: {game_id} ({basename})")

    try:
        topic_number = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"通番 (topic_number) が整数ではありません: {parts[1]}") from exc

    return AudioMetadata(game_id=game_id, topic_number=topic_number, basename=basename)


def transcript_key_for_webm(processing_prefix: str, webm_basename: str) -> str:
    txt_name = webm_basename[: -len(".webm")] + ".txt"
    return f"{processing_prefix}{txt_name}"


def summary_key_for_transcript(processing_prefix: str, transcript_basename: str) -> str:
    if transcript_basename.endswith(".txt"):
        base = transcript_basename[: -len(".txt")]
    else:
        base = transcript_basename
    return f"{processing_prefix}{base}_summary.txt"
