# 07 プロジェクト構成

リポジトリの構成と、各ディレクトリの責務。新しいファイルはこの表に従って置く。

## 構成

```
src/scriba/
  cli.py            引数の解釈と各機能の呼び出し。サブコマンドの入口はここだけ
  config.py         config.toml の読み込み（Config）
  notify.py         macOS 通知
  enrich.py         予定との照合、frontmatter の生成と付加
  classify.py       組織・案件の推定、仕訳ルールの読み書き
  export.py         transcript の転送、未転送の数え上げ
  recording/        録音
    recorder.py       start / stop / status / discard / cleanup とセッション状態（state.json）
    capture.py        録音プロセス本体（sounddevice）、無音検知、自動停止の判定
    audio.py          出力デバイスの検証と切り替え（switchaudio-osx）
    autostop.py       自動停止に使う mic の発話判定
  transcription/    文字起こし
    transcriber.py    Haas / mlx-whisper の呼び出し、トラックのマージ、combined のファイル名
    haas.py           speech.cpp の取得・検証、Haas の認識と発話検出
    dictionary.py     辞書（initial-prompt、置換、フィルタ）
    vad.py            mic トラックの発話区間（Silero VAD）
    worker.py         live モードの逐次文字起こし
  meeting/          自動録音
    watch.py          常駐プロセスと開始・停止の判定（Detector）
    detect.py         会議アプリのマイク使用（CoreAudio）
  calendar/         予定の取得元（アダプタ）
    __init__.py       load_events とイベント形式の日時変換
    json_source.py    イベント形式の JSON
    ics_source.py     iCalendar（ファイル / URL）
  viewer/           HTML ビューア
    render.py         データ収集、静的 HTML、HTMX パーシャル
    server.py         `view --serve` の HTTP サーバーと編集 API
    templates/ static/
tests/              pytest。golden/ は CLI と viewer の出力の期待値
raycast/            Raycast の Script Command
docs/               specs/ adr/ research/ usage.md development.md DESIGN.md
images/             README の画像（アイコンの原本 SVG と PNG、画面の画像、デモ動画）
.agents/skills/     エージェント用の手順（.claude/skills はここへの symlink）
```

## 責務の線

| 線 | 規則 |
|---|---|
| cli ↔ 各機能 | 表示と終了コードは cli が持つ。各機能は値を返すか例外を投げる（`RecorderError`、`AudioGuardError`） |
| calendar ↔ enrich | enrich はイベント形式だけを見る。取得元の違い（ファイル、URL、繰り返しの展開）は calendar の中で閉じる |
| enrich ↔ classify | 組織・案件の推定と仕訳ルールは classify。enrich は照合結果を classify に渡して frontmatter を作る |
| 録音プロセス ↔ CLI | 録音・ワーカー・watch は `python -m scriba <内部サブコマンド>` の別プロセス。状態の受け渡しは state.json とセッション内のフラグファイル（`stopping`、`autostop`、`timeout`、`meeting_end`） |
| 重い依存 | mlx-whisper と Silero VAD（torch）は本体の依存にしない。`uvx` / `uv run --with` の別プロセスで呼ぶ |
| トラック名 | 新規は `system` / `mic`。旧名 `teams` は `transcriber.canonical_track` で `system` に読み替える。ファイル名の書き換えはしない |
