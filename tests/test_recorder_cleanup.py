import json
import os
import time
from datetime import datetime, timedelta

import pytest
from conftest import write_transcript

from scriba.recording import recorder
from scriba.config import Config


def _make_session(cfg: Config, sid: str, *, wavs=("teams_000",), transcribed=True, aged_days=None):
    sdir = cfg.session_dir(sid)
    chunks = sdir / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    (sdir / "transcripts").mkdir(exist_ok=True)
    for w in wavs:
        (chunks / f"{w}.wav").write_bytes(b"RIFF")
        if transcribed:
            write_transcript(sdir, w, [{"start": 0.0, "text": "x"}])
    if aged_days is not None:
        old = time.time() - aged_days * 86400
        os.utime(sdir, (old, old))
    return sdir


def test_cleanup_removes_wav_by_default(tmp_path):
    """保持期間超・文字起こし済み → chunks の WAV を削除（cleanup_target=chunks）。"""
    cfg = Config(base_dir=tmp_path, retention_days=7)
    sdir = _make_session(cfg, "old", aged_days=30)
    removed = recorder.cleanup(cfg)
    assert any("old" in r and "wav" in r for r in removed)
    assert not list((sdir / "chunks").glob("*.wav"))
    assert sdir.exists()  # ディレクトリ自体は残る


def test_cleanup_target_all_removes_session(tmp_path):
    """cleanup_target=all はセッション丸ごと削除。"""
    cfg = Config(base_dir=tmp_path, retention_days=7, cleanup_target="all")
    sdir = _make_session(cfg, "old", aged_days=30)
    removed = recorder.cleanup(cfg)
    assert any("old" in r and "all" in r for r in removed)
    assert not sdir.exists()


def test_cleanup_skips_untranscribed(tmp_path, capsys):
    """未文字起こしのWAVがあるセッションはスキップ（音声を守る）。"""
    cfg = Config(base_dir=tmp_path, retention_days=7)
    sdir = _make_session(cfg, "old", transcribed=False, aged_days=30)
    removed = recorder.cleanup(cfg)
    assert removed == []
    assert list((sdir / "chunks").glob("*.wav"))  # WAV は残る
    assert "スキップ" in capsys.readouterr().out


def test_cleanup_keeps_recent(tmp_path):
    """保持期間内のセッションは触らない。"""
    cfg = Config(base_dir=tmp_path, retention_days=7)
    sdir = _make_session(cfg, "recent", aged_days=1)
    removed = recorder.cleanup(cfg)
    assert removed == []
    assert list((sdir / "chunks").glob("*.wav"))


def test_cleanup_no_sessions_dir(tmp_path):
    cfg = Config(base_dir=tmp_path)
    assert recorder.cleanup(cfg) == []


def test_stop_only_session_ignores_other_session(cfg):
    """自動停止の stop は、録音中が別セッションなら何もしない。"""
    cfg.base_dir.mkdir(parents=True, exist_ok=True)
    cfg.state_file.write_text(json.dumps({"session_id": "new", "record_pid": os.getpid(), "mode": "live"}))
    with pytest.raises(recorder.RecorderError):
        recorder.stop(cfg, only_session="old")
    assert cfg.state_file.exists()


def test_release_state_keeps_other_session(cfg):
    """stateの解放は、中身が自分のセッションのときだけ。"""
    cfg.base_dir.mkdir(parents=True, exist_ok=True)
    cfg.state_file.write_text(json.dumps({"session_id": "new"}))
    recorder._release_state(cfg, "old")
    assert cfg.state_file.exists()
    recorder._release_state(cfg, "new")
    assert not cfg.state_file.exists()


def test_stop_does_not_announce_or_export_incomplete_transcription(cfg, monkeypatch):
    sid = "incomplete"
    sdir = _make_session(cfg, sid, transcribed=False)
    (sdir / "meta.json").write_text(json.dumps({"session_id": sid, "title": "定例"}))
    cfg.state_file.write_text(json.dumps({"session_id": sid, "mode": "live", "record_pid": 123, "started_at": "2026-07-06T09:15:00"}))
    monkeypatch.setattr(recorder, "_alive", lambda _: True)
    monkeypatch.setattr(recorder, "_terminate", lambda *a, **kw: None)
    monkeypatch.setattr(recorder, "_wait_pid", lambda *a, **kw: None)
    monkeypatch.setattr(recorder.audio, "restore_output", lambda _: None)
    messages = []
    monkeypatch.setattr(recorder, "notify", lambda *args: messages.append(args))
    monkeypatch.setattr(recorder.enrich, "enrich_session", lambda *a: pytest.fail("未完了のままenrich"))
    with pytest.raises(recorder.RecorderError, match="未処理"):
        recorder.stop(cfg)
    assert not cfg.state_file.exists()
    assert (sdir / "chunks" / "teams_000.wav").exists()
    assert not any(message == "文字起こし完了" for _, message in messages)


def _stop_after(cfg, monkeypatch, recorded_sec: float):
    """recorded_sec 秒録った live セッションを stop する。"""
    sid = "short"
    sdir = _make_session(cfg, sid)
    (sdir / "meta.json").write_text(json.dumps({"session_id": sid}))
    started = datetime.now() - timedelta(seconds=recorded_sec)
    cfg.state_file.write_text(json.dumps({
        "session_id": sid, "mode": "live", "record_pid": 123,
        "started_at": started.isoformat(timespec="seconds"),
    }))
    monkeypatch.setattr(recorder, "_alive", lambda _: True)
    monkeypatch.setattr(recorder, "_terminate", lambda *a, **kw: None)
    monkeypatch.setattr(recorder, "_wait_pid", lambda *a, **kw: None)
    monkeypatch.setattr(recorder.audio, "restore_output", lambda _: None)
    monkeypatch.setattr(recorder, "notify", lambda *args: None)
    monkeypatch.setattr(recorder.enrich, "enrich_session", lambda *a: None)
    return sdir


def test_stop_discards_recording_shorter_than_min_keep(cfg, monkeypatch):
    """手動で始めた録音でも、min_keep_sec より短ければ文字起こしせず破棄する。"""
    sdir = _stop_after(cfg, monkeypatch, recorded_sec=30)
    with pytest.raises(recorder.RecorderError, match="60秒未満"):
        recorder.stop(cfg)
    assert not sdir.exists()
    assert not cfg.state_file.exists()


def test_stop_keeps_short_recording_when_min_keep_is_zero(tmp_path, monkeypatch):
    cfg = Config(base_dir=tmp_path, min_keep_sec=0)
    sdir = _stop_after(cfg, monkeypatch, recorded_sec=30)
    recorder.stop(cfg)
    assert sdir.exists()


def test_stop_measures_meeting_end_by_when_the_meeting_ended(cfg, monkeypatch):
    """会議の終了で止めた録音は、検知の遅れを含めず、会議が終わった時刻までの長さで判定する。"""
    sdir = _stop_after(cfg, monkeypatch, recorded_sec=65)
    ended = datetime.now() - timedelta(seconds=10)
    (sdir / "meeting_end").write_text(ended.isoformat(timespec="seconds"), encoding="utf-8")
    with pytest.raises(recorder.RecorderError, match="60秒未満"):
        recorder.stop(cfg)
    assert not sdir.exists()


def test_stop_reads_empty_meeting_end_flag(cfg, monkeypatch):
    """終了時刻のない旧版の印でも、止めた時刻までの長さで判定して残す。"""
    sdir = _stop_after(cfg, monkeypatch, recorded_sec=65)
    (sdir / "meeting_end").touch()
    recorder.stop(cfg)
    assert sdir.exists()
    assert json.loads((sdir / "meta.json").read_text())["stopped_reason"] == "meeting_end"
