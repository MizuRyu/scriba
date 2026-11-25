"""常時録音の常駐プロセス。`scriba listen on` で起動する。

OS の既定の入力を録り続け、完成したチャンクを順に文字起こしする。会議の録音（state.json）とは
独立に動く。マイクの許可は watch と同じく起動元のものが使われる。
listen_pause_idle_min を設定すると、寝ている時間帯に入力も発話も無い間は、入力を閉じて待つ。
listen_pause_on_battery を設定すると、電池で動いている間は、入力を閉じて待つ。
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

import sounddevice as sd

from scriba.config import Config
from scriba.listen.backlog import Backlog
from scriba.listen.track import Track
from scriba.meeting import detect
from scriba.notify import notify
from scriba.recording import recorder

POLL_SEC = 3
STALL_SEC = 10  # 音声がこれだけ届かなければ、デバイスが消えたとみなして開き直す


def run(cfg: Config) -> None:
    cfg = cfg.for_listen()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    backlog = Backlog(cfg)
    track: Track | None = None
    device = session = None
    warned = False
    print("listen 開始", flush=True)
    while not stop.is_set():
        current = detect.default_input_device()
        battery = cfg.listen_pause_on_battery and detect.on_battery()
        pause = battery or pausing(cfg, datetime.now(), detect.input_idle_seconds(), time.monotonic() - backlog.spoke_at)
        if track and pause:
            reason = "電池で動いています" if battery else f"入力も発話も {cfg.listen_pause_idle_min} 分ありません"
            print(f"{reason}。入力を閉じます", flush=True)
            track.close()
            track = None
        elif track and (current != device or time.monotonic() - track.heard_at > STALL_SEC):
            # 開き直すと新しいセッションになる。途切れた時間をまたいで本文の時刻をずらさないため
            print("入力デバイスが変わったか、音声が途絶えました。開き直します", flush=True)
            track.close()
            track = None
        if track is None and current is not None and not pause:
            track = _open(cfg)
            device = current
            if track is None and not warned:
                notify("Scriba 警告", "常時録音の入力デバイスを開けません")
            warned = track is None
        recording = track.recording if track else None
        if recording:
            backlog.add(recording[0])
            if recording[0] != session:
                session = recording[0]
                for removed in recorder.cleanup(cfg):
                    print(f"クリーンアップ: {removed}", flush=True)
        worked = backlog.step(recording, detect.mic_in_use(cfg.listen_yield_apps))
        stop.wait(0 if worked else POLL_SEC)
    if track:
        track.close()
    print("listen 終了", flush=True)


def pausing(cfg: Config, now: datetime, idle_sec: float, silent_sec: float) -> bool:
    """入力を閉じておく間は True。設定した時間帯の中で、入力も発話も listen_pause_idle_min 分無い間。

    why not 発話で再開: 入力を閉じている間は音声が届かない。再開の合図は、キーボードやマウスの入力と、時間帯の終わりだけになる。
    """
    limit = cfg.listen_pause_idle_min * 60
    start, end = cfg.listen_pause_from_hour, cfg.listen_pause_until_hour
    # 開始が終了より後なら日付をまたぐ（22 時から 6 時）。同じ値なら終日
    in_hours = start <= now.hour < end if start < end else now.hour >= start or now.hour < end
    return limit > 0 and in_hours and idle_sec >= limit and silent_sec >= limit


def _open(cfg: Config) -> Track | None:
    # PortAudio はデバイスの一覧を初期化の時点で固定する。抜き差しの後は初期化し直さないと新しい既定の入力を開けない
    sd._terminate()
    sd._initialize()
    track = Track(cfg)
    try:
        track.start()
    except Exception as e:
        print(f"入力デバイスを開けません: {e}", flush=True)
        shutil.rmtree(cfg.session_dir(track.session_id), ignore_errors=True)
        return None
    return track


def running_pid(cfg: Config) -> int | None:
    try:
        pid = json.loads(_pid_file(cfg).read_text(encoding="utf-8"))["pid"]
    except (OSError, ValueError, KeyError):
        return None
    if not recorder._alive(pid):
        return None
    # 落ちた後に pid が別のプロセスへ再利用されていたら、常駐とはみなさない
    cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    return pid if "scriba listen run" in cmd else None


def enable(cfg: Config) -> bool:
    """常駐プロセスを起動する。既に動いていれば False。"""
    if running_pid(cfg):
        return False
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    log = open(cfg.logs_dir / "listen.log", "a")
    proc = subprocess.Popen(
        [sys.executable, "-m", "scriba", "listen", "run"], stdout=log, stderr=log, start_new_session=True,
    )
    _pid_file(cfg).write_text(json.dumps({"pid": proc.pid}), encoding="utf-8")
    notify("Scriba", "常時録音を開始しました")
    return True


def disable(cfg: Config) -> bool:
    """常駐プロセスを止める。動いていなければ False。文字起こしの途中なら、そのチャンクを終えてから止まる。"""
    pid = running_pid(cfg)
    _pid_file(cfg).unlink(missing_ok=True)
    if not pid:
        return False
    os.kill(pid, signal.SIGTERM)
    notify("Scriba", "常時録音を停止しました")
    return True


def _pid_file(cfg: Config):
    return cfg.base_dir / "listen.json"
