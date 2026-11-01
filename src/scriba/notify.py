"""macOS通知。"""

import subprocess

# 文言はスクリプトに埋め込まず引数で渡す（引用符やバックスラッシュでスクリプトが壊れないように）
_SCRIPT = "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run"


def notify(title: str, message: str) -> None:
    try:
        subprocess.run(["osascript", "-e", _SCRIPT, title, message], capture_output=True, timeout=5)
    except Exception:
        pass  # 通知失敗で処理は止めない
