# ADR

技術判断の理由と見直し条件。判断をやり直す前に読む。既存の ADR は書き換えず、変わったら新しい番号で追加する。

| 番号 | 判断 |
|---|---|
| [001](001-local-chunked-transcription.md) | 録音はチャンク単位でローカルに文字起こしする（ストリーミングにしない） |
| [002](002-sounddevice-capture.md) | 録音は sounddevice（PortAudio）で行い、ffmpeg の avfoundation を使わない |
| [003](003-heavy-deps-in-subprocess.md) | mlx-whisper と Silero VAD は本体の依存にせず別プロセスで呼ぶ |
| [004](004-calendar-source-adapters.md) | 予定の取得元を json / ics のアダプタに分ける |
| [005](005-system-track-name.md) | 相手側のトラックを system と呼ぶ（旧名 teams も読む） |
| [006](006-haas-default.md) | Haas Q4_K を既定にし、speech.cpp の別プロセスで認識する |
