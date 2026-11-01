# Third-party licenses

scriba はサードパーティのコードを同梱しません。以下は実行時に使うソフトウェアと、そのライセンスです。各ソフトウェアはそれぞれの配布元から入手してください。

## Python の依存（`pyproject.toml`）

| パッケージ | ライセンス |
|---|---|
| [PyYAML](https://github.com/yaml/pyyaml) | MIT |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | MIT |
| [soundfile](https://github.com/bastibe/python-soundfile) | BSD-3-Clause |
| [icalendar](https://github.com/collective/icalendar) | BSD-2-Clause |
| [recurring-ical-events](https://github.com/niccokunzmann/python-recurring-ical-events) | LGPL-3.0-or-later |
| [x-wr-timezone](https://github.com/niccokunzmann/x-wr-timezone)（recurring-ical-events の依存） | LGPL-3.0-or-later |

## 別プロセスで呼ぶもの

| ソフトウェア | ライセンス | 用途 |
|---|---|---|
| [speech.cpp](https://github.com/nyosegawa/speech.cpp) | MIT | Haas / Silero VAD（固定版の実行ファイルを初回取得） |
| [Haas-ja-v1.0](https://huggingface.co/third-intelligence/Haas-ja-v1.0)（[GGUF](https://huggingface.co/sakasegawa/Haas-ja-v1.0-GGUF)） | Apache-2.0 | 日本語の文字起こし（既定は Q4_K） |
| [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) | MIT | 文字起こし（`uvx` で実行） |
| Whisper のモデル（[mlx-community](https://huggingface.co/mlx-community)） | MIT（OpenAI Whisper） | 文字起こし |
| [Silero VAD](https://github.com/snakers4/silero-vad) | MIT | 発話区間（Haas は speech.cpp、Whisper は `uv run --with` で実行） |
| [FFmpeg](https://ffmpeg.org/) | LGPL-2.1-or-later / GPL（ビルドによる） | mlx-whisper の音声読み込み |
| [switchaudio-osx](https://github.com/deweller/switchaudio-osx) | MIT | 出力デバイスの切り替え |
| [BlackHole](https://github.com/ExistentialAudio/BlackHole) | GPL-3.0 | システム音声の取り込み（仮想オーディオデバイス） |

## ビューア

| ソフトウェア | ライセンス | 用途 |
|---|---|---|
| [htmx](https://github.com/bigskysoftware/htmx) | 0BSD | `scriba view --serve` のパーシャル更新（CDN から読み込む） |
