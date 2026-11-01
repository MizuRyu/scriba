import json

import pytest

from scriba.recording import autostop, capture
from scriba.config import Config

SID = "20260706-091500"


@pytest.fixture
def cfg(tmp_path):
    cfg = Config(base_dir=tmp_path)
    (cfg.session_dir(SID) / "transcripts").mkdir(parents=True)
    return cfg


def _vad(cfg, idx, intervals):
    (cfg.session_dir(SID) / "transcripts" / f"mic_{idx:03d}.vad.json").write_text(json.dumps(intervals))


def _close_chunks(track, peaks):
    """チャンクごとのピークを与えて、writerがチャンクを閉じたときの処理を再現する。"""
    for peak in peaks:
        track.peak = peak
        track.idx += 1
        track._check_silence()


def _stopper(cfg, quiet_idx, mic=True):
    teams = capture._Track(cfg, SID, "teams", "dev")
    teams.quiet_idx = quiet_idx
    tracks = [teams, capture._Track(cfg, SID, "mic", "dev")] if mic else [teams]
    stopper = capture._AutoStopper(cfg, SID, tracks)
    stopper.fired_calls = []
    stopper._fire = lambda: stopper.fired_calls.append(quiet_idx)
    return stopper


def test_mic_has_speech(cfg):
    transcripts = cfg.session_dir(SID) / "transcripts"
    assert autostop.mic_has_speech(transcripts, 0) is None  # VAD未処理
    (transcripts / "mic_000.vad.json").write_text("")  # 書き込み途中
    assert autostop.mic_has_speech(transcripts, 0) is None
    _vad(cfg, 0, [])
    assert autostop.mic_has_speech(transcripts, 0) is False
    _vad(cfg, 0, [[1.0, 2.0]])
    assert autostop.mic_has_speech(transcripts, 0) is True


def test_quiet_chunk_counts_only_after_hearing_teams(cfg, monkeypatch):
    """会議前の無音（相手の声を一度も聞いていない）は候補にしない。聞いた後の無音チャンクだけ記録する。"""
    monkeypatch.setattr(capture, "notify", lambda *a: None)
    track = capture._Track(cfg, SID, "teams", "dev")
    _close_chunks(track, [0, 0])
    assert track.quiet_idx is None
    _close_chunks(track, [8000, 0])
    assert track.quiet_idx == 3


def test_stops_when_mic_is_also_silent(cfg):
    _vad(cfg, 3, [])
    stopper = _stopper(cfg, 3)
    stopper.poll(10)
    assert stopper.fired_calls == [3]


def test_waits_for_mic_vad(cfg):
    """micのVADが出るまでは決めない。出たら次の確認で止める。"""
    stopper = _stopper(cfg, 3)
    stopper.poll(10)
    assert stopper.fired_calls == []
    _vad(cfg, 3, [])
    stopper.poll(20)
    assert stopper.fired_calls == [3]


def test_keeps_recording_while_i_speak(cfg):
    """teamsが無音でも、同じチャンクで自分が話していれば止めない。"""
    _vad(cfg, 3, [[10.0, 110.0]])
    stopper = _stopper(cfg, 3)
    stopper.poll(10)
    stopper.poll(20)
    assert stopper.fired_calls == []


def test_teams_only_stops_without_mic(cfg):
    stopper = _stopper(cfg, 3, mic=False)
    stopper.poll(10)
    assert stopper.fired_calls == [3]


def test_disabled(cfg):
    cfg.auto_stop = False
    _vad(cfg, 3, [])
    stopper = _stopper(cfg, 3)
    stopper.poll(10)
    assert stopper.fired_calls == []
