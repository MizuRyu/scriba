# ADR-002 録音は sounddevice で行う

- 状態: 承認
- 日付: 2026-07-02
- 関連: [01 Overview](../specs/01-overview.md)、`src/scriba/recording/capture.py`

## 文脈

初期実装は ffmpeg の avfoundation 入力でチャンク録音していた。トーンを流して欠落を測ると、周期的にサンプルが落ちていた（実測で約 10%、約 107ms/秒）。BlackHole と物理マイクの両方で起きた。

PortAudio（CoreAudio）経由の sounddevice で同じ測定をすると、欠落はゼロだった。

## 決定

- 録音は sounddevice の `RawInputStream` で行い、サンプル数でチャンクを区切る
- ffmpeg は録音には使わない。mlx-whisper が音声を読むのに必要なので、起動時に存在だけ確かめる
- 16kHz を開けないデバイスはネイティブレート（48kHz）で録り、リサンプリングは Whisper 側に任せる

## 見直し条件

- ffmpeg の avfoundation で欠落が再現しなくなったことを、同じトーンテストで確かめたとき
