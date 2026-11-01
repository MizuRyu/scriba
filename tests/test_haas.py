import hashlib
import json
import subprocess
import wave
import zipfile
from pathlib import Path

import pytest

from scriba import cli
from scriba.transcription import haas, transcriber


def _wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\0\0" * 16000)
    return path


def test_haas_chunk_merges_with_legacy_transcript(cfg, monkeypatch):
    wav = _wav(cfg.session_dir("demo") / "chunks" / "system_001.wav")
    out = cfg.session_dir("demo") / "transcripts"
    out.mkdir()
    (out / "teams_000.json").write_text(json.dumps({
        "segments": [{"start": 1, "end": 2, "text": "前の議題"}],
    }))
    cfg.dictionary_path.write_text("terms:\n  - word: ACME\n    priority: high\nreplacements:\n  エーシーエムイー: ACME\n")
    calls = []

    def recognize(base, *args):
        calls.append(args)
        if args[0] == "vad":
            (Path(args[args.index("--split") + 1]) / "region-1.wav").touch()
            return '{"regions":[{"start":3,"end":4}]}'
        assert "--timestamps" not in args
        return json.dumps({"stop": "complete", "text": "エーシーエムイーの確認"})

    monkeypatch.setattr(haas, "_run", recognize)
    entry = transcriber.transcribe_chunk(cfg, "demo", wav)
    assert calls[0][0] == "vad"
    assert calls[1][calls[1].index("--keywords") + 1] == "ACME"
    assert entry["model"] == "haas-ja-v1.0:q4_k"
    assert entry["text_length"] > 0
    assert transcriber.pending_chunks(cfg, "demo") == []
    combined = transcriber.merge_session(cfg, "demo").read_text()
    assert "[00:01]\n前の議題" in combined
    assert "[02:03]\nACMEの確認" in combined


@pytest.mark.parametrize("response", [
    "not json",
    '{"stop":"model_limit","text":"途中","segments":[]}',
    '{"stop":"complete","text":"時刻なし"}',
    '{"stop":"complete","text":"欠落","segments":[]}',
    '{"stop":"complete","text":"不正","segments":[{"start":2,"end":1,"text":"不正"}]}',
    '[]',
])
def test_invalid_result_remains_pending(cfg, monkeypatch, response):
    wav = _wav(cfg.session_dir("retry") / "chunks" / "system_000.wav")
    monkeypatch.setattr(haas, "_run", lambda *a: response)
    with pytest.raises(haas.HaasError):
        transcriber.transcribe_chunk(cfg, "retry", wav)
    assert transcriber.pending_chunks(cfg, "retry") == [wav]
    assert not cfg.perf_log.exists()


def test_silent_mic_writes_vad_without_loading_asr(cfg, monkeypatch):
    wav = _wav(cfg.session_dir("quiet") / "chunks" / "mic_000.wav")
    calls = []

    def detect(base, *args):
        calls.append(args)
        assert args[0] == "vad"
        return '{"regions": []}'

    monkeypatch.setattr(haas, "_run", detect)
    entry = transcriber.transcribe_chunk(cfg, "quiet", wav)
    out = cfg.session_dir("quiet") / "transcripts"
    assert entry["no_speech_skipped"] is True and len(calls) == 1
    assert json.loads((out / "mic_000.json").read_text())["segments"] == []
    assert json.loads((out / "mic_000.vad.json").read_text()) == []


def test_mic_vad_failure_still_attempts_recognition(cfg, monkeypatch):
    wav = _wav(cfg.session_dir("fallback") / "chunks" / "mic_000.wav")

    def recognize(base, *args):
        if args[0] == "vad":
            raise haas.HaasError("VAD unavailable")
        return '{"stop":"complete","text":"発言","segments":[{"start":0,"end":1,"text":"発言"}]}'

    monkeypatch.setattr(haas, "_run", recognize)
    transcriber.transcribe_chunk(cfg, "fallback", wav)
    assert not transcriber.pending_chunks(cfg, "fallback")


def test_subprocess_failure_has_no_transcript_in_message(tmp_path, monkeypatch):
    monkeypatch.setattr(haas, "prepare", lambda base: base / "speech")

    def fail(*a, **kw):
        raise subprocess.CalledProcessError(1, a[0], stderr="認識された本文")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(haas.HaasError) as error:
        haas._run(tmp_path, "asr", "haas-ja-v1.0:q4_k", "input.wav")
    assert "認識された本文" not in str(error.value)


def test_runtime_install_verifies_and_reuses_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(haas.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(haas.platform, "machine", lambda: "arm64")
    archive = tmp_path / "release.zip"
    files = {"speech": b"executable", "libspeech.4.dylib": b"library"}
    with zipfile.ZipFile(archive, "w") as out:
        for name, body in files.items():
            out.writestr(f"release/{name}", body)
    monkeypatch.setattr(haas, "RUNTIME_FILES", {
        name: hashlib.sha256(body).hexdigest() for name, body in files.items()
    })
    monkeypatch.setattr(haas, "ARCHIVE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(haas.urllib.request, "urlopen", lambda *a, **kw: archive.open("rb"))
    executable = haas.prepare(tmp_path)
    assert executable.read_bytes() == b"executable"
    assert executable.stat().st_mode & 0o100
    monkeypatch.setattr(haas.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("downloaded again"))
    assert haas.prepare(tmp_path) == executable


def test_invalid_download_never_installs_executable(tmp_path, monkeypatch):
    monkeypatch.setattr(haas.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(haas.platform, "machine", lambda: "arm64")
    source = tmp_path / "wrong.zip"
    source.write_bytes(b"invalid archive")
    monkeypatch.setattr(haas.urllib.request, "urlopen", lambda *a, **kw: source.open("rb"))
    with pytest.raises(haas.HaasError, match="SHA256"):
        haas.prepare(tmp_path)
    assert not (tmp_path / "models" / f"speech-{haas.VERSION}" / "speech").exists()


def test_setup_model_cli_uses_configured_model(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBA_HOME", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["scriba", "setup-model"])
    calls = []
    monkeypatch.setattr(haas, "setup", lambda *args: calls.append(args))
    cli.main()
    assert calls == [(tmp_path, "haas-ja-v1.0:q4_k")]
    assert "haas-ja-v1.0:q4_k" in capsys.readouterr().out
