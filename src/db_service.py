from __future__ import annotations

import logging

import psycopg2
from psycopg2 import sql

from src.config import Settings

logger = logging.getLogger("stt_app.db")


class TalksRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _connect(self):
        return psycopg2.connect(
            host=self._settings.db_host,
            port=self._settings.db_port,
            dbname=self._settings.db_name,
            user=self._settings.db_user,
            password=self._settings.db_password,
        )

    def update_talk(self, game_id: str, topic_number: int, whole_text: str, summary: str) -> None:
        table = sql.Identifier(self._settings.db_schema, "talks")
        query = sql.SQL(
            """
            UPDATE {table}
            SET whole_text = %s, summary = %s
            WHERE game_id = %s AND topic_number = %s
            """
        ).format(table=table)

        logger.info(
            "DB 更新: %s.talks game_id=%s topic_number=%s",
            self._settings.db_schema,
            game_id,
            topic_number,
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (whole_text, summary, game_id, topic_number))
                if cur.rowcount == 0:
                    raise LookupError(
                        f"更新対象レコードがありません: game_id={game_id}, topic_number={topic_number}"
                    )
            conn.commit()
        logger.info("DB 更新完了: game_id=%s topic_number=%s", game_id, topic_number)
