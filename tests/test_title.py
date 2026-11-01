import argparse
import json

from scriba import cli


def _make_session(cfg, sid, meta):
    sdir = cfg.session_dir(sid)
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return sdir


def test_title_writes_and_preserves_keys(cfg):
    """title 設定で meta.json に title を書き、既存キーは保持する。"""
    _make_session(cfg, "t1", {"started_at": "2026-07-05T14:00:00", "mode": "live"})
    args = argparse.Namespace(command="title", session="t1", title="定例MTG")
    cli._dispatch(args, cfg)
    meta = json.loads((cfg.session_dir("t1") / "meta.json").read_text(encoding="utf-8"))
    assert meta["title"] == "定例MTG"
    assert meta["started_at"] == "2026-07-05T14:00:00"
    assert meta["mode"] == "live"


def test_title_latest_targets_newest(cfg):
    """latest 指定で最新（IDソートの末尾）セッションを対象にする。"""
    _make_session(cfg, "20260705-100000", {"started_at": "a"})
    _make_session(cfg, "20260705-120000", {"started_at": "b"})
    args = argparse.Namespace(command="title", session="latest", title="最新の会議")
    cli._dispatch(args, cfg)
    newest = json.loads((cfg.session_dir("20260705-120000") / "meta.json").read_text(encoding="utf-8"))
    older = json.loads((cfg.session_dir("20260705-100000") / "meta.json").read_text(encoding="utf-8"))
    assert newest["title"] == "最新の会議"
    assert "title" not in older
