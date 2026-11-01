import json

from scriba import export
from scriba.config import Config


def _make_session(cfg: Config, sid: str, *, meta: dict, combined: bool = True) -> None:
    sdir = cfg.session_dir(sid)
    (sdir / "transcripts").mkdir(parents=True)
    (sdir / "meta.json").write_text(json.dumps({"session_id": sid, **meta}, ensure_ascii=False), encoding="utf-8")
    if combined:
        (sdir / "transcripts" / "combined.txt").write_text("本文", encoding="utf-8")


def _cfg(tmp_path) -> Config:
    return Config(base_dir=tmp_path / "scriba", export_dir=str(tmp_path / "inbox"))


def test_project_override_exports_untitled_as_timestamp_name(tmp_path):
    """title 無しでも project を指定すれば yymmdd_hhmm.txt で転送される。"""
    cfg = _cfg(tmp_path)
    _make_session(cfg, "20261025-093000", meta={"started_at": "2026-10-25T09:30:00"})
    from scriba.transcription import transcriber
    combined = transcriber.find_combined(cfg, "20261025-093000")
    combined.rename(combined.parent / transcriber.combined_filename(cfg, "20261025-093000"))

    result = export.export_session(cfg, "20261025-093000", project_override="acme")

    assert result["project"] == "acme"
    assert result["path"] == str(tmp_path / "inbox" / "transcript" / "acme" / "261025_0930.txt")
    meta = json.loads((cfg.session_dir("20261025-093000") / "meta.json").read_text(encoding="utf-8"))
    assert meta["exported_at"]


def test_unclassified_without_project_is_skipped(tmp_path):
    cfg = _cfg(tmp_path)
    _make_session(cfg, "20261025-093000", meta={"started_at": "2026-10-25T09:30:00"})

    result = export.export_session(cfg, "20261025-093000")

    assert result == {"skipped": True, "reason": "unclassified"}
    assert not (tmp_path / "inbox").exists()


def test_list_unexported_returns_only_pending(tmp_path):
    """転送済み・combined 無し・録音中は除き、未転送だけを返す。"""
    cfg = _cfg(tmp_path)
    _make_session(cfg, "a-pending", meta={"title": "定例", "started_at": "2026-10-25T09:30:00"})
    _make_session(cfg, "b-exported", meta={"exported_at": "2026-10-25T10:00:00"})
    _make_session(cfg, "c-no-combined", meta={}, combined=False)
    _make_session(cfg, "d-recording", meta={})
    cfg.state_file.write_text(json.dumps({"session_id": "d-recording"}), encoding="utf-8")

    assert export.list_unexported(cfg) == [
        {"id": "a-pending", "title": "定例", "started_at": "2026-10-25T09:30:00", "reason": "unclassified"},
    ]


def test_export_subdir_template(tmp_path):
    cfg = Config(base_dir=tmp_path / "scriba", export_dir=str(tmp_path / "inbox"), export_subdir="{project}/meetings")
    _make_session(cfg, "20261025-093000", meta={"started_at": "2026-10-25T09:30:00"})

    result = export.export_session(cfg, "20261025-093000", project_override="acme")

    assert result["path"] == str(tmp_path / "inbox" / "acme" / "meetings" / "combined.txt")


def test_without_export_dir_nothing_is_exported_or_counted(tmp_path):
    cfg = Config(base_dir=tmp_path / "scriba")
    _make_session(cfg, "20261025-093000", meta={"started_at": "2026-10-25T09:30:00"})

    assert export.export_session(cfg, "20261025-093000", project_override="acme") == {
        "skipped": True, "reason": "export_dir not set",
    }
    assert export.list_unexported(cfg) == []
