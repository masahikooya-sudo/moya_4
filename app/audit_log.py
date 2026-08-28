"""ユーザーが何を入力したか・どのファイルをアップロードしたかを記録する利用ログ。

注意: AUDIT_LOG_RAW_INPUT (既定 true) が有効な場合、マスキング前の生データ
(個人情報を含む可能性がある)がそのままログファイルに書き込まれる。
このツールは個人情報を隠すためのものだが、このログを有効にすると別の場所に
個人情報が平文で保存されることになるため、ログファイルのアクセス権限・
保管期間の管理は運用者の責任で行うこと。
"""

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

from . import config

os.makedirs(config.AUDIT_LOG_DIR, exist_ok=True)
_LOG_PATH = os.path.join(config.AUDIT_LOG_DIR, "audit.log")

_logger = logging.getLogger("pii_masking_audit")
_logger.setLevel(logging.INFO)
_logger.propagate = False

if not _logger.handlers:
    # 日付が変わるタイミング(サーバーのローカル時刻の午前0時)でログファイルを
    # 分割する。ロール後のファイルは "audit.log.YYYY-MM-DD" という名前になり、
    # 現在の日付分は常に "audit.log" に書き込まれる。
    _file_handler = TimedRotatingFileHandler(
        _LOG_PATH,
        when="midnight",
        interval=1,
        backupCount=config.AUDIT_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    _file_handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_file_handler)

    # docker compose logs でも確認できるよう標準出力にも出す。
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_stream_handler)


def _entity_counts(detections: list) -> dict:
    counts = {}
    for detection in detections:
        counts[detection["entity_type"]] = counts.get(detection["entity_type"], 0) + 1
    return counts


def _write(user: str, record: dict, content: str) -> None:
    # "user" を先頭フィールドにするため、record より先に詰める。
    ordered = {"user": user or "anonymous"}
    ordered.update(record)
    ordered["timestamp"] = datetime.now(timezone.utc).isoformat()
    if config.AUDIT_LOG_RAW_INPUT:
        ordered["input_content"] = content
    _logger.info(json.dumps(ordered, ensure_ascii=False))


def log_text_request(
    user: str, text: str, style: str, entities: list, detections: list
) -> None:
    _write(
        user,
        {
            "type": "text",
            "style": style,
            "entities_requested": entities,
            "detection_count": len(detections),
            "entities_detected": _entity_counts(detections),
        },
        text,
    )


def log_file_request(
    user: str,
    filename: str,
    ext: str,
    style: str,
    entities: list,
    detections: list,
    raw_text: str,
) -> None:
    _write(
        user,
        {
            "type": "file",
            "filename": filename,
            "extension": ext,
            "style": style,
            "entities_requested": entities,
            "detection_count": len(detections),
            "entities_detected": _entity_counts(detections),
        },
        raw_text,
    )
