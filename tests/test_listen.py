import json
from datetime import datetime

from scriba.config import Config, load
from scriba.listen.backlog import Backlog
from scriba.listen.track import Track


def test_listen_sessions_live_apart_from_meeting_sessions(tmp_path, monkeypatch):
    cfg = Config(base_dir=tmp_path)
    assert cfg.for_listen().session_dir("s1") == tmp_path / "listen" / "s1"
    assert cfg.session_dir("s1") == tmp_path / "sessions" / "s1"
    # 置き場の名前は config.toml から変えられない
    (tmp_path / "config.toml").write_text('sessions_name = "elsewhere"\n', encoding="utf-8")
    monkeypatch.setenv("SCRIBA_HOME", str(tmp_path))
    assert load().sessions_dir == tmp_path / "sessions"


class _Clock:
    def __init__(self, *times: str):
        self.times = [datetime.fromisoformat(t) for t in times]

    def __call__(self) -> datetime:
        return self.times.pop(0) if len(self.times) > 1 else self.times[0]


def _close_chunk(track: Track) -> None:
    """録音スレッドがチャンクを閉じたときと同じ順で進める。"""
    track.idx += 1
    track._chunk_closed()


def test_track_keeps_session_within_the_hour_and_switches_when_the_hour_changes(tmp_path):
    cfg = Config(base_dir=tmp_path).for_listen()
    track = Track(cfg, now=_Clock("2026-01-05T10:57:00", "2026-01-05T10:59:00", "2026-01-05T11:01:00"))
    assert track.recording == ("20260105-105700", 0)

    _close_chunk(track)  # 10:59。同じ時なので同じセッションの次のチャンク
    assert track.recording == ("20260105-105700", 1)

    _close_chunk(track)  # 11:01。時が変わったので新しいセッションの最初のチャンク
    assert track.recording == ("20260105-110100", 0)
    assert track.dir == cfg.session_dir("20260105-110100") / "chunks"
    meta = json.loads((cfg.session_dir("20260105-110100") / "meta.json").read_text(encoding="utf-8"))
    assert meta["started_at"] == "2026-01-05T11:01:00"
    assert meta["tracks"] == ["mic"]


def test_track_opened_again_within_the_same_second_gets_its_own_session(tmp_path):
    cfg = Config(base_dir=tmp_path).for_listen()
    first = Track(cfg, now=_Clock("2026-01-05T10:57:00"))
    again = Track(cfg, now=_Clock("2026-01-05T10:57:00"))  # 入力が続けて切り替わると、同じ秒に開き直す
    assert first.recording == ("20260105-105700", 0)
    assert again.recording == ("20260105-105701", 0)


def _chunk(cfg: Config, session_id: str, idx: int):
    chunks = cfg.session_dir(session_id) / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    (cfg.session_dir(session_id) / "transcripts").mkdir(exist_ok=True)
    wav = chunks / f"mic_{idx:03d}.wav"
    wav.write_bytes(b"RIFF")
    return wav


def _backlog(cfg: Config, texts: dict[str, str], merged: list[str]) -> Backlog:
    """texts はチャンク名ごとの認識結果。空文字は発話なし、無いチャンクは失敗。"""

    def transcribe(cfg, session_id, wav):
        text = texts[wav.stem]
        out = cfg.session_dir(session_id) / "transcripts" / f"{wav.stem}.json"
        out.write_text(json.dumps({"text": text, "segments": []}), encoding="utf-8")
        return {"no_speech_skipped": not text}

    return Backlog(cfg, transcribe=transcribe, merge=lambda cfg, session_id: merged.append(session_id))


def test_backlog_leaves_the_chunk_being_written(tmp_path):
    cfg = Config(base_dir=tmp_path).for_listen()
    done, writing = _chunk(cfg, "s1", 0), _chunk(cfg, "s1", 1)
    merged: list[str] = []
    backlog = _backlog(cfg, {"mic_000": "こんにちは"}, merged)

    assert backlog.step(("s1", 1), busy=False) is True
    assert backlog.step(("s1", 1), busy=False) is False
    assert merged == ["s1"]
    assert done.exists() and writing.exists()  # 発話のある音声は残す


def test_backlog_waits_while_another_app_uses_the_microphone(tmp_path):
    cfg = Config(base_dir=tmp_path).for_listen()
    _chunk(cfg, "s1", 0)
    merged: list[str] = []
    backlog = _backlog(cfg, {"mic_000": "こんにちは"}, merged)

    assert backlog.step(("s1", 1), busy=True) is False
    assert merged == []
    assert backlog.step(("s1", 1), busy=False) is True


def test_backlog_drops_audio_without_speech_and_sessions_without_text(tmp_path):
    cfg = Config(base_dir=tmp_path).for_listen()
    silent = _chunk(cfg, "s1", 0)
    _chunk(cfg, "s2", 0)
    merged: list[str] = []
    backlog = _backlog(cfg, {"mic_000": ""}, merged)

    assert backlog.step(("s2", 0), busy=False) is True
    assert not silent.exists()
    assert backlog.step(("s2", 0), busy=False) is False  # s1 は録音を終えていて、発話が無い
    assert not cfg.session_dir("s1").exists()
    assert cfg.session_dir("s2").exists()  # 録音中のセッションは消さない
    assert merged == []


def test_backlog_keeps_sessions_with_text_and_stops_scanning_them(tmp_path):
    cfg = Config(base_dir=tmp_path).for_listen()
    _chunk(cfg, "s1", 0)
    backlog = _backlog(cfg, {"mic_000": "メモ"}, [])

    assert backlog.step(None, busy=False) is True
    assert backlog.step(None, busy=False) is False
    assert cfg.session_dir("s1").exists()
    assert backlog.sessions == []


def test_backlog_keeps_audio_when_transcription_fails(tmp_path):
    cfg = Config(base_dir=tmp_path).for_listen()
    wav = _chunk(cfg, "s1", 0)
    backlog = _backlog(cfg, {}, [])  # 認識結果が無いので KeyError で失敗する

    assert backlog.step(None, busy=False) is True
    assert backlog.step(None, busy=False) is False  # 同じチャンクを繰り返し試さない
    assert wav.exists()
    assert cfg.session_dir("s1").exists()
