import json
import time
from datetime import datetime, timezone

import pytest

from scriba import calendar, enrich
from scriba.config import Config

ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:weekly-1
SUMMARY:ACME 定例
DTSTART;TZID=Asia/Tokyo:20260629T091500
DTEND;TZID=Asia/Tokyo:20260629T100000
RRULE:FREQ=WEEKLY
ORGANIZER:mailto:alice@acme.example
END:VEVENT
BEGIN:VEVENT
UID:once-utc
SUMMARY:Beta レビュー
DTSTART:20260706T050000Z
DURATION:PT30M
STATUS:TENTATIVE
END:VEVENT
BEGIN:VEVENT
UID:cancelled
SUMMARY:中止
DTSTART;TZID=Asia/Tokyo:20260706T110000
DTEND;TZID=Asia/Tokyo:20260706T113000
STATUS:CANCELLED
END:VEVENT
BEGIN:VEVENT
UID:all-day
SUMMARY:休暇
DTSTART;VALUE=DATE:20260706
DTEND;VALUE=DATE:20260707
END:VEVENT
BEGIN:VEVENT
UID:other-day
SUMMARY:別の日
DTSTART;TZID=Asia/Tokyo:20260707T091500
DTEND;TZID=Asia/Tokyo:20260707T100000
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture(autouse=True)
def tokyo(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


def test_ics_expands_recurrence_and_drops_non_meetings(tmp_path):
    (tmp_path / "cal.ics").write_text(ICS, encoding="utf-8")
    cfg = Config(base_dir=tmp_path, calendar_source="ics", calendar_path=str(tmp_path / "cal.ics"))
    events = calendar.load_events(cfg, datetime(2026, 7, 6, 9, 20))
    assert events == [
        {"id": "weekly-1", "subject": "ACME 定例", "start": "2026-07-06T00:15:00", "end": "2026-07-06T01:00:00",
         "organizer": "alice@acme.example", "showAs": "busy"},
        {"id": "once-utc", "subject": "Beta レビュー", "start": "2026-07-06T05:00:00", "end": "2026-07-06T05:30:00",
         "organizer": "", "showAs": "tentative"},
    ]


def test_ics_event_matches_like_json(tmp_path):
    (tmp_path / "cal.ics").write_text(ICS, encoding="utf-8")
    cfg = Config(base_dir=tmp_path, calendar_source="ics", calendar_path=str(tmp_path / "cal.ics"),
                 enrich_organizations={"acme.example": "ACME"}, enrich_projects=[{"alias": "acme", "keywords": ["ACME"]}])
    start = datetime(2026, 7, 6, 9, 16)
    result = enrich.match_event(calendar.load_events(cfg, start), start)
    meta = enrich.build_enrich_meta(result["event"], cfg)
    assert meta == {"title": "ACME 定例", "date": "2026-07-06", "start": "09:15", "end": "10:00",
                    "organization": "ACME", "project": "acme"}


def test_ics_unreadable_returns_empty(tmp_path, capsys):
    cfg = Config(base_dir=tmp_path, calendar_source="ics", calendar_path=str(tmp_path / "missing.ics"))
    assert calendar.load_events(cfg, datetime(2026, 7, 6)) == []
    assert "カレンダーを読めませんでした" in capsys.readouterr().err


def test_calendar_path_alone_means_json(tmp_path):
    events = [{"id": "1", "subject": "x", "start": "2026-07-06T00:15:00.0000000", "end": "2026-07-06T01:00:00"}]
    (tmp_path / "today.json").write_text(json.dumps({"events": events}), encoding="utf-8")
    cfg = Config(base_dir=tmp_path, calendar_path=str(tmp_path / "today.json"))
    assert calendar.load_events(cfg, datetime(2026, 7, 6)) == events


def test_no_source_means_no_events(tmp_path):
    assert calendar.load_events(Config(base_dir=tmp_path), datetime(2026, 7, 6)) == []


def test_unknown_source_warns(tmp_path, capsys):
    cfg = Config(base_dir=tmp_path, calendar_source="caldav", calendar_path="x")
    assert calendar.load_events(cfg, datetime(2026, 7, 6)) == []
    assert "caldav" in capsys.readouterr().err


def test_json_missing_file(tmp_path):
    cfg = Config(base_dir=tmp_path, calendar_source="json", calendar_path=str(tmp_path / "none.json"))
    assert calendar.load_events(cfg, datetime(2026, 7, 6)) == []


def _json_cfg(tmp_path, start):
    events = [{"id": "1", "subject": "x", "start": start, "end": start}]
    (tmp_path / "today.json").write_text(json.dumps({"events": events}), encoding="utf-8")
    return Config(base_dir=tmp_path, calendar_source="json", calendar_path=str(tmp_path / "today.json"))


def test_json_morning_event_is_not_stale(tmp_path, capsys):
    # 東京の朝 8 時は UTC では前日の 23 時
    morning = datetime.now().astimezone().replace(hour=8, minute=0, second=0, microsecond=0)
    start = morning.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + ".0000000"
    calendar.load_events(_json_cfg(tmp_path, start), morning)
    assert "古い可能性" not in capsys.readouterr().err


def test_json_past_event_warns_stale(tmp_path, capsys):
    calendar.load_events(_json_cfg(tmp_path, "2020-01-01T00:15:00.0000000"), datetime(2026, 7, 6))
    assert "古い可能性" in capsys.readouterr().err
