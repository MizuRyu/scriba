"""F1: 会議（Teams など、config.toml の meeting_apps）の開始・終了に合わせて録音を自動で開始・停止する常駐プロセス。

Raycast から `scriba watch on` で起動する。録音プロセスと同じくマイクの許可は
起動元（Raycast）のものが使われる。
"""

import json
import os
import signal
import subprocess
import sys
import time

from scriba.meeting import detect
from scriba.recording import recorder
from scriba.config import Config
from scriba.notify import notify

POLL_SEC = 2
START_SEC = 4  # マイク使用がこれだけ続いたら会議開始
STOP_SEC = 10  # マイク不使用がこれだけ続いたら会議終了
# 参加前の待機画面でも会議アプリはマイクを開く（通話中と区別できない）。待機だけで
# 終わった短いセッションは、stop が min_keep_sec で破棄する
_STARTED = "(start)"  # 開始を指示したがセッションをまだ見ていない


class Detector:
    """会議アプリのマイク使用の変化から、録音の開始・停止を決める。

    開始するのは会議に入った最初だけ。会議中に手動・無音で止まったら、その会議では
    再開しない。会議の終わりに止めるのは、その会議で録っていたセッションだけ。
    """

    def __init__(self, start_sec: float = START_SEC, stop_sec: float = STOP_SEC):
        self.start_sec, self.stop_sec = start_sec, stop_sec
        self.in_meeting = False
        self.pending_since: float | None = None
        self.recorded: str | None = None  # この会議で録音していたセッション
        self.stopping: str | None = None  # 停止を指示したセッション（stop が state を解放するまで残る）

    def step(self, now: float, mic_on: bool, session: str | None) -> str | None:
        if session is None:
            self.stopping = None
        elif session == self.stopping:
            session = None
        if self._settled(now, mic_on):
            self.in_meeting = mic_on
            if not mic_on:
                return self._meeting_ended(session)
        if not self.in_meeting:
            return None
        if session:
            self.recorded = session
            return None
        if self.recorded:
            return None
        self.recorded = _STARTED
        return "start"

    def _settled(self, now: float, mic_on: bool) -> bool:
        """マイク状態の変化が、開始・終了それぞれの時間だけ続いたら True。"""
        if mic_on == self.in_meeting:
            self.pending_since = None
            return False
        if self.pending_since is None:
            self.pending_since = now
        if now - self.pending_since < (self.start_sec if mic_on else self.stop_sec):
            return False
        self.pending_since = None
        return True

    def _meeting_ended(self, session: str | None) -> str | None:
        ended, self.recorded = self.recorded, None
        if session and session == ended:
            self.stopping = session
            return "stop"
        return None


def run(cfg: Config) -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    detector = Detector()
    stops: list[subprocess.Popen] = []
    print("watch 開始", flush=True)
    while True:
        # 終わった stop を回収する（常駐し続けるので、回収しないと defunct が残る）
        stops = [p for p in stops if p.poll() is None]
        state = recorder.load_state(cfg)
        session = state["session_id"] if state else None
        action = detector.step(time.monotonic(), detect.mic_in_use(cfg.meeting_apps), session)
        if action == "start":
            _start(cfg)
        elif action == "stop":
            stops.append(_stop(cfg, session))
        time.sleep(POLL_SEC)


def _start(cfg: Config) -> None:
    # 連続した会議: 前の会議の stop が state を解放するまで待つ
    deadline = time.monotonic() + 60
    while recorder.load_state(cfg) and time.monotonic() < deadline:
        time.sleep(1)
    print("会議を検知。録音を開始", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "scriba", "start"], capture_output=True, text=True, timeout=120,
        )
        print(result.stdout + result.stderr, flush=True)
        failed = result.returncode != 0
    except subprocess.TimeoutExpired:
        # 固まった start に常駐ループを止めさせない（run が子を kill して回収済み）
        print("start が応答しないため中断", flush=True)
        failed = True
    if failed:
        notify("Scriba 警告", "会議を検知しましたが録音を開始できませんでした")


def _stop(cfg: Config, session_id: str) -> subprocess.Popen:
    print(f"会議の終了を検知。{session_id} を停止", flush=True)
    (cfg.session_dir(session_id) / "meeting_end").touch()
    # stop は後処理まで長くかかるので待たない（次の会議の開始を遅らせない）
    return subprocess.Popen(
        [sys.executable, "-m", "scriba", "stop", "--only-session", session_id],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )


def running_pid(cfg: Config) -> int | None:
    try:
        pid = json.loads(_pid_file(cfg).read_text(encoding="utf-8"))["pid"]
    except (OSError, ValueError, KeyError):
        return None
    return pid if _is_watch_process(pid) else None


def _is_watch_process(pid: int) -> bool:
    """pid が今も watch の常駐プロセスか。落ちた後に pid が別のプロセスへ再利用されていたら False。"""
    if not recorder._alive(pid):
        return False
    cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    return "scriba watch run" in cmd


def enable(cfg: Config) -> bool:
    """常駐プロセスを起動する。既に動いていれば False。"""
    if running_pid(cfg):
        return False
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    log = open(cfg.logs_dir / "watch.log", "a")
    proc = subprocess.Popen(
        [sys.executable, "-m", "scriba", "watch", "run"], stdout=log, stderr=log, start_new_session=True,
    )
    _pid_file(cfg).write_text(json.dumps({"pid": proc.pid}), encoding="utf-8")
    notify("Scriba", "自動録音を有効にしました（会議の開始・終了で録音を開始・停止）")
    return True


def disable(cfg: Config) -> bool:
    """常駐プロセスを止める。動いていなければ False。録音中のセッションには触れない。"""
    pid = running_pid(cfg)
    _pid_file(cfg).unlink(missing_ok=True)
    if not pid:
        return False
    os.kill(pid, signal.SIGTERM)
    notify("Scriba", "自動録音を無効にしました")
    return True


def _pid_file(cfg: Config):
    return cfg.base_dir / "watch.json"
