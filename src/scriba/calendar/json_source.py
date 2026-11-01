"""イベント形式の JSON（{"events": [...]}）を読む。

当日の予定を外部（Power Automate などの定期実行）が書き出し、ファイル同期で届く運用を想定する。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from scriba.calendar import parse_utc, to_local


def load(path: str) -> list[dict]:
    file = Path(path).expanduser()
    if not file.exists():
        return []
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    events = data.get("events", [])
    # 書き出し側が止まっていると前日以前の予定が残る
    if events and not _starts_today(events[0].get("start", "")):
        print(f"警告: カレンダーデータが古い可能性があります（{file} の更新を確認）", file=sys.stderr)
    return events


def _starts_today(start: str) -> bool:
    # start は UTC。ローカルの朝の予定は UTC では前日の日付になる
    try:
        return to_local(parse_utc(start)).date() == datetime.now().astimezone().date()
    except ValueError:
        return False
