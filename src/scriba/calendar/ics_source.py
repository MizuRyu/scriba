"""iCalendar（.ics のファイルまたは http(s) URL）を読み、イベント形式に変換する。

繰り返し予定は対象日の回に展開する。終日予定と取り消された予定は会議ではないので除く。
"""

import sys
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import icalendar
import recurring_ical_events

_TIMEOUT_SEC = 10
_UTC_FORMAT = "%Y-%m-%dT%H:%M:%S"


def load(location: str, around: datetime) -> list[dict]:
    try:
        raw = _read(location)
        cal = icalendar.Calendar.from_ical(raw)
    except (OSError, ValueError) as e:
        print(f"警告: カレンダーを読めませんでした（{location}）: {e}", file=sys.stderr)
        return []
    day = around.astimezone().date()
    start = datetime.combine(day, time.min).astimezone()
    occurrences = recurring_ical_events.of(cal).between(start, start + timedelta(days=1))
    events = [_to_event(ev) for ev in occurrences if _is_meeting(ev)]
    return sorted(events, key=lambda e: e["start"])


def _read(location: str) -> bytes:
    if location.startswith(("http://", "https://")):
        with urllib.request.urlopen(location, timeout=_TIMEOUT_SEC) as r:
            return r.read()
    return Path(location).expanduser().read_bytes()


def _is_meeting(ev) -> bool:
    if str(ev.get("STATUS", "")).upper() == "CANCELLED":
        return False
    return isinstance(ev.decoded("DTSTART"), datetime)


def _to_event(ev) -> dict:
    start = ev.decoded("DTSTART")
    end = ev.decoded("DTEND") if ev.get("DTEND") else start + ev.decoded("DURATION", timedelta())
    return {
        "id": str(ev.get("UID", "")),
        "subject": str(ev.get("SUMMARY", "")),
        "start": _utc(start),
        "end": _utc(end),
        "organizer": str(ev.get("ORGANIZER", "")).removeprefix("mailto:").removeprefix("MAILTO:"),
        "showAs": _show_as(ev),
    }


def _utc(dt: datetime | date) -> str:
    # 浮動時刻（TZ なし）はローカル時刻として扱う
    aware = dt if dt.tzinfo else dt.astimezone()
    return aware.astimezone(timezone.utc).strftime(_UTC_FORMAT)


def _show_as(ev) -> str:
    if str(ev.get("STATUS", "")).upper() == "TENTATIVE":
        return "tentative"
    if str(ev.get("TRANSP", "")).upper() == "TRANSPARENT":
        return "free"
    return "busy"
