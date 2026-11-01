"""micトラックの発話区間検出（Silero VAD）。

large-v3 は自分が話していない間の無音micチャンクで定型句を幻聴する。発話区間と
重ならないセグメントを捨てるため、文字起こし時に区間を求めて保存する。
torch が要るため scriba 本体の依存にはせず、mlx-whisper と同様に別プロセスで実行する。
"""

import json
import subprocess
from pathlib import Path

# 既定（threshold 0.5、最短250ms）は小声・短い相槌（「うん」「確かに」）を落とす。緩めて増える
# 幻聴は定型句フィルタで消える文言だけだった（2026-10-23/25、micチャンク346本で比較）
VAD_KWARGS = {"threshold": 0.35, "speech_pad_ms": 200, "min_speech_duration_ms": 100}

_SCRIPT = f"""
import json, sys
KWARGS = {VAD_KWARGS!r}
import soundfile as sf, torch
from silero_vad import get_speech_timestamps, load_silero_vad
audio, sr = sf.read(sys.argv[1], dtype="float32")
ts = get_speech_timestamps(
    torch.from_numpy(audio), load_silero_vad(), sampling_rate=sr, return_seconds=True, **KWARGS
)
print(json.dumps([[t["start"], t["end"]] for t in ts]))
"""


def speech_intervals(wav: Path) -> list[list[float]]:
    """発話区間 [[start, end], ...]（秒）を返す。"""
    cmd = [
        "uv", "run", "--no-project",
        "--with", "silero-vad", "--with", "soundfile",
        "python", "-c", _SCRIPT, str(wav),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


def vad_path(transcript_json: Path) -> Path:
    return transcript_json.with_name(f"{transcript_json.stem}.vad.json")


def overlaps(seg: dict, intervals: list[list[float]]) -> bool:
    return any(seg["start"] < end and start < seg["end"] for start, end in intervals)
