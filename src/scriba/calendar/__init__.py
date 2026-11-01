"""F8: 予定の取得元。config.toml の calendar_source でアダプタを選ぶ。

どのアダプタも scriba のイベント形式の dict を返す:
  id, subject, start, end, organizer, showAs
  start / end は UTC の ISO 8601（タイムゾーン表記なし。小数秒は任意）
"""

import sys
from datetime import datetime, timezone

from scriba.config import Config


def load_events(cfg: Config, around: datetime) -> list[dict]:
    """around を含む日の予定。取得元が未設定なら空。"""
    source = cfg.calendar_source or ("json" if cfg.calendar_path else "")
    if source == "json":
        from scriba.calendar import json_source

        return json_source.load(cfg.calendar_path)
    if source == "ics":
        from scriba.calendar import ics_source

        return ics_source.load(cfg.calendar_path, around)
    if source:
        print(f"警告: calendar_source「{source}」は未対応です（json | ics）", file=sys.stderr)
    return []


def parse_utc(dt_str: str) -> datetime:
    """イベント形式の UTC 日時文字列を aware な datetime に変換。"""
    # "2026-07-06T00:15:00.0000000" → naive UTC
    cleaned = dt_str.split(".")[0] if "." in dt_str else dt_str
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_local(dt: datetime) -> datetime:
    return dt.astimezone()
