"""system トラック（旧名 teams）の読み書き。新旧どちらのセッションも同じ結果になる。"""

import json

import pytest

from conftest import write_transcript
from scriba.transcription import transcriber, worker
from scriba.viewer import render

SID = "20260706-091500"


def _session(cfg, system_name: str):
    sdir = cfg.session_dir(SID)
    (sdir / "chunks").mkdir(parents=True)
    (sdir / "meta.json").write_text(json.dumps({"started_at": "2026-07-06T09:15:00"}), encoding="utf-8")
    write_transcript(sdir, f"{system_name}_000", [{"start": 0.0, "end": 2.0, "text": "相手の発言"}])
    write_transcript(sdir, "mic_000", [{"start": 5.0, "end": 7.0, "text": "自分の発言"}])
    for name in (f"{system_name}_000", f"{system_name}_001", "mic_000"):
        (sdir / "chunks" / f"{name}.wav").write_bytes(b"")
    return sdir


@pytest.mark.parametrize("name", ["system", "teams"])
def test_merge_labels_both_names_as_other_party(cfg, name):
    _session(cfg, name)
    text = transcriber.merge_session(cfg, SID).read_text(encoding="utf-8")
    assert text == "[00:00] [相手]\n相手の発言\n\n[00:05] [自分]\n自分の発言\n"


@pytest.mark.parametrize("name", ["system", "teams"])
@pytest.mark.parametrize("only", ["system", "teams"])
def test_track_filter_accepts_either_name(cfg, name, only):
    _session(cfg, name)
    text = transcriber.merge_session(cfg, SID, only_tracks={only}).read_text(encoding="utf-8")
    assert text == "[00:00]\n相手の発言\n"


@pytest.mark.parametrize("name", ["system", "teams"])
def test_system_chunks_counted_under_either_name(cfg, name):
    sdir = _session(cfg, name)
    assert transcriber.count_system(sdir / "chunks", ".wav") == 2
    assert transcriber.count_system(sdir / "transcripts", ".json") == 1


def test_pending_and_completion_for_system_chunks(cfg):
    sdir = _session(cfg, "system")
    pending = transcriber.pending_chunks(cfg, SID)
    assert [w.stem for w in pending] == ["system_001"]
    assert worker._is_complete(sdir / "chunks" / "system_000.wav", sdir / "chunks")
    assert not worker._is_complete(sdir / "chunks" / "system_001.wav", sdir / "chunks")


def test_saved_legacy_filter_shows_system_active(cfg):
    html = render._track_filter_html({"has_mic": True, "track_filter": "teams"}, SID)
    assert "detail-tab active\" onclick=\"remerge('20260706-091500','system')" in html


def test_stopping_worker_does_not_retry_failed_chunk_forever(cfg, monkeypatch):
    sdir = _session(cfg, "system")
    (sdir / "stopping").touch()

    def fail(*args):
        raise RuntimeError("recognizer unavailable")

    monkeypatch.setattr(transcriber, "transcribe_chunk", fail)
    monkeypatch.setattr(worker.time, "sleep", lambda _: pytest.fail("停止後に再試行し続けている"))
    with pytest.raises(RuntimeError, match="未処理"):
        worker.run(cfg, SID)
    assert (sdir / "chunks" / "system_001.wav").exists()
