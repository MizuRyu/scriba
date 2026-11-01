"""F1: 会議終了の自動検知。

systemのチャンクが丸ごと無音（無音警告と同じ条件）で、同じ時間帯のmicチャンクにも
発話がなければ会議終了とみなす。micはworkerが作るVAD結果で判断するため、
VADを待ってから決める（自分だけが話し続けている間に止めないため）。
"""

import json
from pathlib import Path


def mic_has_speech(transcripts: Path, idx: int) -> bool | None:
    """micチャンクにVADの発話区間があるか。VAD未処理・書き込み途中なら None。"""
    try:
        intervals = json.loads((transcripts / f"mic_{idx:03d}.vad.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return bool(intervals)
