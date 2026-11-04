"""CLI と viewer の出力を golden ファイルと突き合わせ、構成の変更で挙動が変わらないことを確かめる。

入口は `scriba` の CLI と viewer の HTTP だけを使う（内部の import 先に依存しない）。
golden の更新: `SCRIBA_UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py`
"""

import http.server
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import write_transcript

GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.environ.get("SCRIBA_UPDATE_GOLDEN") == "1"

# 架空の会議。UTC 00:15 = JST 09:15
EVENT = {
    "id": "evt-1",
    "subject": "【ACME】定例 7/6",
    "start": "2026-07-06T00:15:00.0000000",
    "end": "2026-07-06T01:00:00.0000000",
    "organizer": "alice@sales.acme.example",
    "showAs": "busy",
}
CONFIG = """\
model = "mlx-community/whisper-large-v3-turbo"
capture_mic = true
export_dir = "{export_dir}"
calendar_path = "{calendar_path}"

[enrich.organizations]
"acme.example" = "ACME"

[[enrich.projects]]
alias = "acme"
keywords = ["ACME"]

[[enrich.projects]]
alias = "beta"
keywords = ["Beta"]
"""


def check(name: str, actual: str) -> None:
    path = GOLDEN / name
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    assert path.exists(), f"golden がありません: {name}（SCRIBA_UPDATE_GOLDEN=1 で作る）"
    assert actual == path.read_text(encoding="utf-8"), f"golden 不一致: {name}"


def scrub(text: str, home: Path) -> str:
    for root in (home.parent.resolve(), home.parent):
        text = text.replace(str(root), "<TMP>")
    text = re.sub(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}", "<NOW>", text)
    return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "<TS>", text)


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    home = tmp_path / "home"
    home.mkdir()
    (tmp_path / "calendar.json").write_text(json.dumps({"events": [EVENT]}, ensure_ascii=False), encoding="utf-8")
    (home / "config.toml").write_text(
        CONFIG.format(export_dir=tmp_path / "out", calendar_path=tmp_path / "calendar.json"), encoding="utf-8"
    )
    (home / "dict.yaml").write_text("replacements:\n  エーシーエムイー: ACME\n", encoding="utf-8")
    _two_track_session(home / "sessions" / "20260706-091500")
    _single_track_session(home / "sessions" / "20260707-140000")
    perf = [
        {"session": "20260706-091500", "chunk": "teams_000", "audio_duration_sec": 120.0, "process_time_sec": 6.0},
        {"session": "20260706-091500", "chunk": "mic_000", "audio_duration_sec": 120.0, "process_time_sec": 5.0},
    ]
    (home / "logs").mkdir()
    (home / "logs" / "performance.jsonl").write_text("".join(json.dumps(e) + "\n" for e in perf), encoding="utf-8")
    monkeypatch.setenv("SCRIBA_HOME", str(home))
    monkeypatch.setattr(subprocess, "run", _no_external)
    yield home
    monkeypatch.delenv("TZ")
    time.tzset()


def _no_external(cmd, *a, **kw):
    # osascript（通知）と open（ブラウザ）を実行しない
    return subprocess.CompletedProcess(cmd, 0, "", "")


def _two_track_session(sdir: Path) -> None:
    (sdir / "chunks").mkdir(parents=True)
    for name in ("teams_000", "teams_001", "mic_000"):
        (sdir / "chunks" / f"{name}.wav").write_bytes(b"")
    meta = {
        "session_id": sdir.name, "started_at": "2026-07-06T09:15:00", "stopped_at": "2026-07-06T09:59:00",
        "mode": "live", "chunk_duration": 120, "tracks": ["teams", "mic"],
    }
    (sdir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    write_transcript(sdir, "teams_000", [
        {"start": 0.0, "end": 4.0, "text": "エーシーエムイーの件です"},
        {"start": 30.0, "end": 33.0, "text": "ご視聴ありがとうございました"},
    ])
    write_transcript(sdir, "teams_001", [{"start": 1.0, "end": 3.0, "text": "次の議題に移ります"}])
    write_transcript(sdir, "mic_000", [
        {"start": 10.0, "end": 12.0, "text": "承知しました"},
        {"start": 60.0, "end": 62.0, "text": "私はあなたを愛しています"},
    ])
    (sdir / "transcripts" / "mic_000.vad.json").write_text("[[9.5, 13.0]]", encoding="utf-8")


def _single_track_session(sdir: Path) -> None:
    (sdir / "chunks").mkdir(parents=True)
    meta = {"session_id": sdir.name, "started_at": "2026-07-07T14:00:00", "mode": "live", "tracks": ["teams"]}
    (sdir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    write_transcript(sdir, "teams_000", [{"start": 2.0, "end": 5.0, "text": "Beta の進捗確認"}])


def run_cli(home: Path, capsys, *argv: str) -> str:
    from scriba import cli

    sys.argv = ["scriba", *argv]
    try:
        cli.main()
    except SystemExit as e:
        assert not e.code, f"終了コード {e.code}"
    out = capsys.readouterr()
    return scrub(out.out + out.err, home)


def tree(root: Path, home: Path) -> str:
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            lines.append(f"## {p.relative_to(root)}\n{scrub(p.read_text(encoding='utf-8'), home)}")
    return "\n".join(lines)


def test_cli_flow(home, capsys):
    log = [
        run_cli(home, capsys, "merge", "20260706-091500"),
        run_cli(home, capsys, "merge", "20260707-140000"),
        run_cli(home, capsys, "enrich", "20260706-091500"),
        run_cli(home, capsys, "status"),
        run_cli(home, capsys, "export"),
        run_cli(home, capsys, "export", "20260707-140000", "--project", "beta"),
        run_cli(home, capsys, "status"),
        run_cli(home, capsys, "title", "latest", "Beta 振り返り"),
        run_cli(home, capsys, "merge", "20260706-091500", "--track", "teams"),
        run_cli(home, capsys, "dict", "show"),
    ]
    check("cli_flow.txt", "\n=====\n".join(log))
    check("cli_sessions.txt", tree(home / "sessions", home))
    check("cli_export.txt", tree(home.parent / "out", home))
    check("cli_rules.txt", scrub((home / "classification_rules.jsonl").read_text(encoding="utf-8"), home))


def test_status_while_recording_counts_system_chunks(home, capsys):
    (home / "state.json").write_text(json.dumps({
        "session_id": "20260706-091500", "mode": "live", "record_pid": os.getpid(), "worker_pid": None,
        "prev_output": None, "started_at": "2026-07-06T09:15:00",
    }), encoding="utf-8")
    out = run_cli(home, capsys, "status")
    assert "チャンク: 2 / 文字起こし済み: 2" in out


def test_static_view(home, capsys):
    run_cli(home, capsys, "merge", "20260706-091500")
    run_cli(home, capsys, "enrich", "20260706-091500")
    run_cli(home, capsys, "view")
    html = (home / "view" / "index.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r"let DATA = (\{.*?\});\n", html, re.S).group(1))
    check("view_data.json", scrub(json.dumps(data, ensure_ascii=False, indent=1), home))


@pytest.fixture
def server(home, monkeypatch):
    from scriba import cli

    servers = []

    class Capture(http.server.ThreadingHTTPServer):
        def __init__(self, addr, handler):
            super().__init__(("127.0.0.1", 0), handler)
            servers.append(self)

    monkeypatch.setattr(http.server, "ThreadingHTTPServer", Capture)
    sys.argv = ["scriba", "view", "--serve"]
    t = threading.Thread(target=cli.main, daemon=True)
    t.start()
    while not servers:
        time.sleep(0.01)
    base = f"http://127.0.0.1:{servers[0].server_address[1]}"
    yield base
    servers[0].shutdown()
    t.join(timeout=5)


def call(base: str, method: str, path: str, body: dict | None = None) -> str:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return f"{r.status}\n{r.read().decode()}"
    except urllib.error.HTTPError as e:
        return f"{e.code}\n{e.read().decode()}"


def test_serve(home, server, capsys):
    run_cli(home, capsys, "merge", "20260706-091500")
    run_cli(home, capsys, "enrich", "20260706-091500")
    log = [
        call(server, "GET", "/partial/sessions"),
        call(server, "GET", "/partial/session/20260706-091500"),
        call(server, "GET", "/partial/settings"),
        call(server, "GET", "/partial/performance"),
        call(server, "POST", "/merge?id=20260706-091500&track=mic"),
        call(server, "GET", "/partial/session/20260706-091500"),
        call(server, "POST", "/title?id=20260707-140000", {"title": "Beta 定例"}),
        call(server, "POST", "/export?id=20260707-140000"),
        call(server, "POST", "/export?id=20260707-140000&project=beta"),
        call(server, "POST", "/dict", {"terms": [{"word": "ACME"}], "replacements": [], "filters": []}),
        call(server, "POST", "/enrich", {"organizations": {"acme.example": "ACME"},
                                         "projects": [{"alias": "acme", "keywords": ["ACME", "エーシー"]}]}),
        call(server, "GET", "/partial/sessions"),
    ]
    check("serve.txt", scrub("\n=====\n".join(log), home))
    check("serve_config.toml", scrub((home / "config.toml").read_text(encoding="utf-8"), home))


def test_serve_pages(home, server):
    log = [
        call(server, "GET", "/"),
        call(server, "GET", "/data.json"),
        call(server, "GET", "/static/app.js").split("\n", 1)[0],
        call(server, "GET", "/static/style.css").split("\n", 1)[0],
        call(server, "GET", "/static/none.js"),
        call(server, "GET", "/nope"),
        call(server, "POST", "/nope"),
        call(server, "POST", "/merge"),
        call(server, "POST", "/discard?id=missing"),
        call(server, "POST", "/discard?id=20260707-140000"),
    ]
    check("serve_pages.txt", scrub("\n=====\n".join(log), home))
    assert not (home / "sessions" / "20260707-140000").exists()


def _module(*names: str):
    """v1（平置き）と v2（サブパッケージ）のどちらの構成でも同じテストを流すため。"""
    for name in names:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError(names)


def test_start_stop_flow(home, capsys, monkeypatch):
    audio = _module("scriba.recording.audio", "scriba.audio")
    restored = []
    monkeypatch.setattr(audio, "validate_and_switch", lambda cfg: "Speakers")
    monkeypatch.setattr(audio, "mic_available", lambda cfg: True)
    monkeypatch.setattr(audio, "restore_output", restored.append)
    monkeypatch.setattr(shutil, "which", lambda name: f"<which>/{name}")
    launched = []
    real_popen = subprocess.Popen

    def fake_popen(cmd, **kw):
        launched.append(" ".join(cmd).replace(sys.executable, "<PY>"))
        # 録音プロセスは stop の SIGINT まで生き、ワーカーはすぐ終わる。終了を即回収して生存判定を正しくする
        proc = real_popen(["sleep", "30" if "record" in cmd else "0.1"])
        threading.Thread(target=proc.wait, daemon=True).start()
        return proc

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    event = {**EVENT, "id": "evt-now", "subject": "【ACME】臨時",
             "start": now.strftime("%Y-%m-%dT%H:%M:%S") + ".0000000",
             "end": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S") + ".0000000"}
    (home.parent / "calendar.json").write_text(json.dumps({"events": [event]}, ensure_ascii=False), encoding="utf-8")

    log = [run_cli(home, capsys, "start")]
    state = json.loads((home / "state.json").read_text(encoding="utf-8"))
    sid = state["session_id"]
    # min_keep_sec で破棄されない長さの会議にする
    state["started_at"] = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
    (home / "state.json").write_text(json.dumps(state), encoding="utf-8")
    sdir = home / "sessions" / sid
    system = json.loads((sdir / "meta.json").read_text(encoding="utf-8"))["tracks"][0]
    (sdir / "chunks" / f"{system}_000.wav").write_bytes(b"")
    write_transcript(sdir, f"{system}_000", [{"start": 1.0, "end": 3.0, "text": "臨時の議題です"}])
    log += [run_cli(home, capsys, "merge", sid), run_cli(home, capsys, "stop"), "\n".join(launched), repr(restored)]
    assert not (home / "state.json").exists()

    def norm(text: str) -> str:
        text = text.replace(sid, "<SID>")
        # 予定は実行時刻に合わせて作るので、frontmatter の日時も実行ごとに変わる
        text = re.sub(r"^date: \d{4}-\d{2}-\d{2}$", "date: <DATE>", text, flags=re.M)
        text = re.sub(r'^(start|end): "\d{2}:\d{2}"$', r'\1: "<HH:MM>"', text, flags=re.M)
        return re.sub(r"\d{6}_\d{4}", "<STEM>", text)

    check("start_stop.txt", norm("\n=====\n".join(log)))
    check("start_stop_session.txt", norm(tree(sdir, home)))
    check("start_stop_export.txt", norm(tree(home.parent / "out", home)))
