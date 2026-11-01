import json
import time

import pytest

from conftest import write_transcript
from scriba import enrich
from scriba.config import Config
from scriba.transcription import transcriber

SID = "20260706-091500"
EVENT = {"id": "evt-1", "subject": "【ACME】定例", "start": "2026-07-06T00:15:00.0000000",
         "end": "2026-07-06T01:00:00.0000000", "organizer": "alice@acme.example", "showAs": "busy"}
FRONTMATTER = """---
title: 【ACME】定例
date: 2026-07-06
start: "09:15"
end: "10:00"
organization: ACME
project: acme
source_session: 20260706-091500
---
"""


@pytest.fixture(autouse=True)
def tokyo(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config(base_dir=tmp_path, enrich_organizations={"acme.example": "ACME"},
                  enrich_projects=[{"alias": "acme", "keywords": ["ACME"]}])


def _session(cfg: Config, meta: dict):
    sdir = cfg.session_dir(SID)
    write_transcript(sdir, "system_000", [{"start": 1.0, "end": 3.0, "text": "議題です"}])
    (sdir / "meta.json").write_text(json.dumps({"started_at": "2026-07-06T09:15:00", **meta}, ensure_ascii=False),
                                    encoding="utf-8")
    return transcriber.merge_session(cfg, SID)


def test_frontmatter_is_added_to_titled_combined(cfg):
    _session(cfg, {"title": "【ACME】定例", "enrich": EVENT})

    result = enrich.enrich_session(cfg, SID)

    path = transcriber.find_combined(cfg, SID)
    assert result["path"] == str(path)
    assert path.name == "260706_0915_【ACME】定例.txt"
    assert path.read_text(encoding="utf-8") == FRONTMATTER + "\n[00:01]\n議題です\n"


def test_enrich_renames_untitled_combined_to_title(cfg):
    _session(cfg, {})
    meta_file = cfg.session_dir(SID) / "meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    meta.update(title="【ACME】定例", enrich=EVENT)
    meta_file.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    enrich.enrich_session(cfg, SID)

    names = [p.name for p in (cfg.session_dir(SID) / "transcripts").glob("*.txt")]
    assert names == ["260706_0915_【ACME】定例.txt"]


def test_enrich_and_merge_are_idempotent(cfg):
    _session(cfg, {"title": "【ACME】定例", "enrich": EVENT})
    enrich.enrich_session(cfg, SID)
    first = transcriber.find_combined(cfg, SID).read_text(encoding="utf-8")

    enrich.enrich_session(cfg, SID)
    transcriber.merge_session(cfg, SID)
    enrich.enrich_session(cfg, SID)

    assert transcriber.find_combined(cfg, SID).read_text(encoding="utf-8") == first


def test_legacy_combined_txt_is_still_found(cfg):
    sdir = cfg.session_dir(SID)
    (sdir / "transcripts").mkdir(parents=True)
    (sdir / "meta.json").write_text(json.dumps({"started_at": "2026-07-06T09:15:00", "enrich": EVENT}),
                                    encoding="utf-8")
    (sdir / "transcripts" / "combined.txt").write_text("[00:01]\n議題です\n", encoding="utf-8")

    enrich.enrich_session(cfg, SID)

    path = transcriber.find_combined(cfg, SID)
    assert path.read_text(encoding="utf-8").startswith("---\ntitle: 【ACME】定例\n")
