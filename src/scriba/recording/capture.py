"""音声キャプチャ: sounddevice (PortAudio/CoreAudio) によるチャンク録音。

ffmpegのavfoundation入力は周期的なサンプル落ち（実測で約10%、約107ms/秒）が
あるため使わない。PortAudio経由なら欠落ゼロ（2026-07-02 トーンテストで実証）。
"""

import array
import queue
import signal
import subprocess
import sys
import threading
import time

import sounddevice as sd
import soundfile as sf

from scriba.recording import autostop
from scriba.config import Config
from scriba.notify import notify

_BYTES_PER_FRAME = 2  # int16 mono
# チャンク全体のピークがこれ未満なら無音（ルーティング断の疑い）とみなす。
# int16フルスケール32767に対して約-56dB。実会話のピークは数千以上
_SILENCE_PEAK = 50


class _Track:
    def __init__(self, cfg: Config, session_id: str, name: str, device: str):
        self.name = name
        self.device = device
        self.multi_output_device = cfg.multi_output_device
        self.chunk_sec = cfg.chunk_duration
        self.sr = cfg.sample_rate
        self.dir = cfg.session_dir(session_id) / "chunks"
        self.q: queue.Queue = queue.Queue()
        self.idx = 0
        self.frames = 0
        self.file = None
        self.peak = 0
        self.silence_warned = False
        self.heard = False  # 一度でも音があったか
        self.quiet_idx: int | None = None  # 音を聞いた後で最後に丸ごと無音だったチャンク
        self.thread = threading.Thread(target=self._writer, daemon=True)

    def start(self) -> None:
        try:
            self.stream = self._open_stream(self.sr)
        except Exception:
            # 16kHz非対応デバイスはネイティブレートで録る（Whisper側でリサンプリングされる）
            self.sr = 48000
            self.stream = self._open_stream(self.sr)
        self.stream.start()
        self.thread.start()
        print(f"[{self.name}] 録音開始: {self.device} @ {self.sr}Hz", flush=True)

    def _open_stream(self, sr: int) -> sd.RawInputStream:
        return sd.RawInputStream(
            device=self.device, samplerate=sr, channels=1, dtype="int16",
            callback=self._callback,
        )

    def _callback(self, indata, frames, t, status) -> None:
        if status:
            print(f"[{self.name}] {status}", file=sys.stderr, flush=True)
        self.q.put(bytes(indata))

    def _writer(self) -> None:
        chunk_frames = self.chunk_sec * self.sr
        while True:
            data = self.q.get()
            if data is None:
                return
            if self.file is None:
                path = self.dir / f"{self.name}_{self.idx:03d}.wav"
                self.file = sf.SoundFile(path, "w", samplerate=self.sr, channels=1, subtype="PCM_16")
            self.file.buffer_write(data, dtype="int16")
            samples = array.array("h", data)
            block_peak = max(max(samples), -min(samples))
            self.peak = max(self.peak, block_peak)
            self.frames += len(data) // _BYTES_PER_FRAME
            if self.frames >= chunk_frames:
                self.file.close()
                self.file = None
                self.frames = 0
                self.idx += 1
                self._check_silence()

    def _check_silence(self) -> None:
        if self.peak < _SILENCE_PEAK and not self.silence_warned:
            self.silence_warned = True
            msg = f"{self.name}トラックが無音です。"
            if self.name == "system":
                msg += f"会議アプリのスピーカーが「{self.multi_output_device}」か確認してください"
            print(msg, flush=True)
            notify("Scriba 警告", msg)
        if self.peak >= _SILENCE_PEAK:
            self.silence_warned = False  # 復旧したら次の無音でまた警告する
            self.heard = True
        elif self.heard:
            self.quiet_idx = self.idx - 1
        self.peak = 0

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()
        self.q.put(None)
        self.thread.join(timeout=10)
        if self.file:
            self.file.close()
            self.file = None


def run(cfg: Config, session_id: str, use_mic: bool) -> None:
    tracks = [_Track(cfg, session_id, "system", cfg.device_system)]
    if use_mic:
        tracks.append(_Track(cfg, session_id, "mic", cfg.device_mic))

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    max_sec = cfg.max_recording_min * 60

    for t in tracks:
        t.start()
    started = time.time()
    stopper = _AutoStopper(cfg, session_id, tracks)
    timed_out = False
    while not stop.is_set():
        time.sleep(0.2)
        if stop.is_set():
            break
        stopper.poll(time.time() - started)
        if time.time() - started >= max_sec:
            timed_out = True
            break
    for t in tracks:
        t.close()
    if timed_out:
        # タイムアウトフラグをセッションに残す
        timeout_flag = cfg.session_dir(session_id) / "timeout"
        timeout_flag.touch()
        notify("Scriba", f"録音が{cfg.max_recording_min}分でタイムアウトしました。切り忘れの可能性があります。")
        print(f"タイムアウト（{cfg.max_recording_min}分）", flush=True)
    print("録音プロセス終了", flush=True)


class _AutoStopper:
    """会議終了を検知して `scriba stop` を一度だけ起動する。

    systemのチャンクが丸ごと無音になったら、同じチャンクのmicのVAD結果を待って判断する。
    相手の声を一度も聞いていない間（会議前の待機）は無音チャンクを数えない。
    """

    _INTERVAL_SEC = 10

    def __init__(self, cfg: Config, session_id: str, tracks: list[_Track]):
        self.enabled = cfg.auto_stop
        self.session_id = session_id
        self.session = cfg.session_dir(session_id)
        self.system = tracks[0]
        self.has_mic = len(tracks) > 1
        self.checked: int | None = None  # 判定を終えた無音チャンク
        self.next_check = self._INTERVAL_SEC
        self.fired = False

    def poll(self, elapsed: float) -> None:
        if self.fired or not self.enabled or elapsed < self.next_check:
            return
        self.next_check = elapsed + self._INTERVAL_SEC
        idx = self.system.quiet_idx
        if idx is None or idx == self.checked:
            return
        speech = autostop.mic_has_speech(self.session / "transcripts", idx) if self.has_mic else False
        if speech is None:
            return  # VAD待ち
        self.checked = idx
        if not speech:
            self._fire()

    def _fire(self) -> None:
        self.fired = True
        (self.session / "autostop").touch()
        print("会議終了を検知（system・micとも1チャンク発話なし）。自動停止します", flush=True)
        notify("Scriba", "相手・自分とも発話がないため録音を自動停止します")
        # stop は録音プロセス（自分）にSIGINTを送って待つので、別セッションで起動する
        subprocess.Popen(
            [sys.executable, "-m", "scriba", "stop", "--only-session", self.session_id],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
