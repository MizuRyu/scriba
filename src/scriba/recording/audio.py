"""Audio Guard: 録音開始時のデバイス検証と出力切替（switchaudio-osx使用）。

複数出力装置は仮想デバイスのため、イヤフォン抜き差しのOS自動フォールバックが
効かない。普段は物理デバイスを出力にしておき、録音中だけ切り替える。
"""

import shutil
import subprocess

from scriba.config import Config


class AudioGuardError(Exception):
    pass


def _sas(*args: str) -> str:
    result = subprocess.run(
        ["SwitchAudioSource", *args], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def current_output() -> str:
    return _sas("-c", "-t", "output")


def current_input() -> str:
    return _sas("-c", "-t", "input")


def list_devices(kind: str) -> list[str]:
    return [line for line in _sas("-a", "-t", kind).splitlines() if line]


def validate_and_switch(cfg: Config) -> str | None:
    """バリデーションして出力を複数出力装置へ切り替える。

    戻り値: 切り替え前の出力デバイス名（復元用）。切り替え不要なら None。
    """
    if shutil.which("SwitchAudioSource") is None:
        raise AudioGuardError(
            "SwitchAudioSource が見つかりません。`brew install switchaudio-osx` でインストールしてください"
        )

    outputs = list_devices("output")
    inputs = list_devices("input")

    if cfg.multi_output_device not in outputs:
        raise AudioGuardError(
            f"出力装置「{cfg.multi_output_device}」が見つかりません。\n"
            "Audio MIDI設定で複数出力装置（BlackHole 2ch + ヘッドフォン）を作成してください。\n"
            f"利用可能な出力: {', '.join(outputs)}"
        )

    if cfg.device_system not in inputs:
        raise AudioGuardError(
            f"録音デバイス「{cfg.device_system}」が見つかりません。\n"
            "BlackHole 2ch がインストールされているか確認してください"
            "（認識されない場合は coreaudiod の再起動）。\n"
            f"利用可能な入力: {', '.join(inputs)}"
        )

    if "blackhole" in current_input().lower():
        raise AudioGuardError(
            f"システムの入力デバイスが「{current_input()}」になっています。\n"
            "この状態では会議アプリに自分の声が届きません。入力をマイクに戻してください"
        )

    # micの有無は呼び出し側が mic_available() で判定する（ここでは扱わない）
    return validate_output_switch(cfg)


def validate_output_switch(cfg: Config) -> str | None:
    prev = current_output()
    if prev == cfg.multi_output_device:
        return None
    _sas("-s", cfg.multi_output_device, "-t", "output")
    return prev


def mic_available(cfg: Config) -> bool:
    return cfg.device_mic in list_devices("input")


def restore_output(prev: str | None) -> None:
    if prev:
        try:
            _sas("-s", prev, "-t", "output")
        except subprocess.CalledProcessError:
            pass  # 元デバイスが抜かれている場合など。OSのフォールバックに任せる
