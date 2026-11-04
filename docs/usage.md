# 使い方

## 前提

- macOS 14.2 以降 / Apple Silicon
- [uv](https://docs.astral.sh/uv/)（文字起こしと VAD を別プロセスで呼ぶのに使う）
- [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole)、[switchaudio-osx](https://github.com/deweller/switchaudio-osx)、ffmpeg

## セットアップ

```bash
brew install blackhole-2ch switchaudio-osx ffmpeg
uv tool install --editable .
scriba setup-model
```

1. **Audio MIDI 設定で複数出力装置を作る。** メンバーは BlackHole 2ch とヘッドフォン。日本語の macOS では「複数出力装置」、英語では "Multi-Output Device" という名前になる。名前が違うときは `multi_output_device` に設定する
2. **会議アプリのスピーカーを複数出力装置にする。** Teams なら「設定 > デバイス > スピーカー」。会議アプリはシステム既定ではなくアプリ内で選んだデバイスへ出力するため、ここが物理デバイスのままだと相手の声が BlackHole に届かない
3. 録音中だけ、scriba が OS の出力を複数出力装置へ切り替え、停止時に元へ戻す（イヤフォンの抜き差しに OS が追従できるように、普段は物理デバイスのままにしておく）

Haas と発話検出用の Silero VAD は端末内で動く。`setup-model` は固定版 speech.cpp と重み（約353 MB）を取得・検証する。初回の文字起こしでも自動取得する。ffmpeg は従来の mlx-whisper に必要で、録音開始時にも存在を確認する。

## コマンド

```bash
scriba start                      # 録音開始（live: 逐次文字起こし）
scriba start --mode record-only   # 録音のみ（stop後にまとめて文字起こし）
scriba status                     # 状態確認（自動録音の有効/無効、未転送の件数も出す）
scriba stop                       # 停止（残チャンクの文字起こしを待って完了通知）

scriba setup-model                # Haas の実行ファイルと重みを事前に準備
scriba transcribe <session-id>    # 未処理チャンクの一括文字起こし
scriba transcribe --all
scriba merge <session-id> [--until <分>] [--track system|mic|both]   # combined を作り直す
scriba title <session-id|latest> <会議名>                             # 会議名を後から付ける
scriba enrich <session-id|latest>                                    # 予定との照合をやり直す
scriba export [<session-id>] [--project <案件>]                       # transcript を転送する

scriba view                       # HTMLビューアを生成して開く（静的）
scriba view --serve               # HTTPサーバー配信（5秒自動更新、Discard、辞書・Enrich 編集）
scriba discard [<session-id>]     # セッションを破棄（録音中なら中止して破棄、IDなしなら最新）
scriba dict show | validate       # 辞書の確認（Whisper の initial-prompt は上限224トークン）
scriba cleanup                    # 保持期間を超えたWAVを削除（start時にも自動実行）
scriba watch on | off | toggle    # 自動録音
```

`uv tool install` していなければ `uv run scriba` で呼べる。

## 自分の声も録る（2 トラック）

`capture_mic = true` にすると、マイクを併録して `[自分]` / `[相手]` のラベルで分ける。ヘッドフォンを使うこと（スピーカーだとマイクに相手の声が入る）。mic トラックは Silero VAD で発話区間を求め、区間外の幻聴を捨てる。

自分が一言も話さなかった会議では、`scriba merge <id> --track system` かビューアの「相手のみ」で mic トラックを外せる。

## 自動録音

```bash
scriba watch on
```

会議アプリがマイクを使い始めて約 4 秒で録音を始め、使わなくなって約 10 秒で止める。

- 会議アプリは `meeting_apps`（bundle id の接頭辞）で指定する。既定は Teams（`com.microsoft.teams`）。Zoom を足すなら `["com.microsoft.teams", "us.zoom.xos"]`
- 参加前の待機画面でもアプリはマイクを開くので録音が始まる。`min_keep_sec`（既定 60 秒）未満で終わった録音は破棄する
- 会議中に手で止めた録音は、その会議では再開しない
- **マイクの許可を持つアプリ（Raycast など）から有効にする。** 録音プロセスはマイクの許可を起動元から受け継ぐ。許可のないターミナルから起動すると無音で録れることがある
- 再起動・ログアウトで常駐プロセスは止まる
- ログ: `{base_dir}/logs/watch.log`

## Raycast

`raycast/` の Script Command を Raycast に登録する。

| スクリプト | 動作 |
|---|---|
| `toggle-scriba.sh` | 録音の開始・停止 |
| `toggle-scriba-record-only.sh` | record-only での開始・停止 |
| `toggle-scriba-watch.sh` | 自動録音の有効・無効 |
| `scriba-status.sh` / `scriba-view.sh` / `scriba-serve.sh` | 状態、ビューア |

スクリプトは `scriba` が PATH にあることを前提にする。`uv tool install` の置き場（`~/.local/bin`）が Raycast の PATH にないときは、スクリプトの `PATH` を自分の環境に合わせる。

## 予定との照合（任意）

録音開始時刻の ±10 分にある予定から会議名を付け、組織と案件を推定して frontmatter に書く。詳しい仕様は [06](specs/06-calendar-enrich.md)。

```toml
# iCalendar（Google カレンダーの「iCal 形式の非公開 URL」、Outlook の公開 URL、.ics ファイル）
calendar_source = "ics"
calendar_path = "https://calendar.example.com/private/basic.ics"

# または、外部の定期実行が書き出すイベント形式の JSON
calendar_source = "json"
calendar_path = "~/Sync/today-calendar.json"

[enrich.organizations]
"acme.example" = "ACME"

[[enrich.projects]]
alias = "acme"
keywords = ["ACME"]
```

非公開の iCal URL は予定へのアクセス権そのもの。config.toml を共有したり、Issue に貼ったりしない。

## 転送（任意）

案件が決まったセッションの combined を `{export_dir}/{export_subdir}` にコピーする。`export_dir` が未設定なら転送しない。

```toml
export_dir = "~/notes/inbox"
export_subdir = "transcript/{project}"   # 既定
```

- `scriba stop` は、会議名と照合結果がそろっていれば自動で転送する
- 未分類のセッションは `scriba export <id> --project <案件>` か、ビューアのドロップダウンで案件を選んで転送する。選んだ案件は仕訳ルールとして覚え、次回から同じ定例を自動で分類する
- `scriba export --project <案件>`（session 省略）は、未転送のうち未分類のものだけにその案件を当てる

## 設定

`{base_dir}/config.toml`。`base_dir` の既定は `~/scriba` で、環境変数 `SCRIBA_HOME` で変えられる。

| キー | 既定 | 内容 |
|---|---|---|
| `device_system` | `BlackHole 2ch` | 相手の声（システム音声）の入力デバイス |
| `device_mic` | `外部マイク` | 自分の声の入力デバイス（`capture_mic = true` のときだけ使う）。英語の macOS では "External Microphone" など |
| `multi_output_device` | `複数出力装置` | 録音中に切り替える出力（英語の macOS では "Multi-Output Device"） |
| `chunk_duration` | `120` | チャンク長（秒） |
| `sample_rate` | `16000` | サンプリングレート（開けないデバイスは 48000 で録る） |
| `mode` | `live` | `live`（逐次）\| `record-only` |
| `model` | `haas-ja-v1.0:q4_k` | `haas-` で始まる名前は speech.cpp、それ以外は従来の mlx-whisper のモデル |
| `language` | `ja` | 文字起こしの言語 |
| `transcribe_on_stop` | `true` | record-only の stop 時にまとめて文字起こしする |
| `capture_mic` | `false` | マイクを併録して 2 トラックにする |
| `session_format` | `%Y%m%d-%H%M%S` | セッション ID（strftime） |
| `retention_days` | `7` | WAV の保持日数 |
| `cleanup_target` | `chunks` | `chunks`（WAV だけ削除）\| `all`（セッションごと削除） |
| `max_recording_min` | `180` | 切り忘れ対策のタイムアウト（分） |
| `auto_stop` | `true` | system・mic とも 2 分チャンク丸ごと発話がなければ自動停止 |
| `min_keep_sec` | `60` | これより短い録音は停止時に破棄する（秒。0 で無効）。手動で始めた録音も対象 |
| `serve_timeout_min` | `180` | `view --serve` の自動停止（分。0 で無効） |
| `dict_path` | 空 | 辞書のパス（空なら `{base_dir}/dict.yaml`） |
| `filters_enabled` | `true` | 幻聴定型・単独相槌のフィルタ |
| `calendar_source` | 空 | `json` \| `ics`（空で `calendar_path` があれば `json`） |
| `calendar_path` | 空 | json: ファイル / ics: ファイルまたは http(s) URL |
| `export_dir` | 空 | 転送先のルート（空なら転送しない） |
| `export_subdir` | `transcript/{project}` | 転送先ルート配下のフォルダ |
| `meeting_apps` | `["com.microsoft.teams"]` | 自動録音で会議中とみなすアプリ（bundle id の接頭辞） |
| `[enrich.organizations]` | なし | メールドメイン → 組織名 |
| `[[enrich.projects]]` | なし | 案件の `alias` と `keywords`（定義順に評価） |

## 辞書

`{base_dir}/dict.yaml`。ビューア（`view --serve` の Dictionary タブ）からも編集できる。

```yaml
terms:          # priority: high の語を Haas の keywords / Whisper の initial-prompt に渡す
  - word: GPT-Realtime
    priority: high
replacements:   # 文字起こし後の一括置換（誤: 正）
  設計ショー: 設計書
filters:        # この文言だけのセグメントを捨てる（内蔵の幻聴定型に加える）
  - ご視聴ありがとうございました
```

Haas の用語には `word: Haas=ハース` の形で読みも指定できる。用語を渡す場合の時刻は最大12秒の発話区間を示す。用語なしでは認識結果のセグメント時刻を使う。

置換・フィルタを変えた後は `scriba merge <id>` で過去のセッションにも反映できる。認識ヒントの変更には元音声の再認識が必要。

## データの場所

```
{base_dir}/
├── config.toml
├── dict.yaml
├── models/speech-0.10.0/         # 検証済みの実行ファイルと共有ライブラリ
├── state.json                   # 録音中の状態
├── watch.json                   # 自動録音の常駐プロセス
├── classification_rules.jsonl   # 仕訳ルール
├── logs/                        # performance.jsonl, watch.log
├── view/index.html              # scriba view の出力
└── sessions/{session_id}/
    ├── meta.json
    ├── chunks/                  # system_000.wav / mic_000.wav（retention_days 後に削除）
    └── transcripts/
        ├── system_000.json ...  # 認識結果（mic は .vad.json も）
        └── yymmdd_hhmm[_会議名].txt   # combined（話者ラベル付きの最終テキスト）
```

Haas / Silero の重みは speech.cpp のキャッシュ（macOS は `~/Library/Caches/speech.cpp/models`）に置く。`SPEECH_MODEL_DIR` で変更できる。Whisper を使う既存設定は `model` をそのまま保てば引き続き動く。

録音・文字起こし・ログはすべて端末内に置く。外部へ送るのは、`calendar_path` に URL を設定したときの ics の取得と、初回のモデル・依存の取得だけ。

## トラブルシュート

| 症状 | 確認すること |
|---|---|
| 「system トラックが無音です」と通知される | 会議アプリのスピーカーが複数出力装置か。複数出力装置に BlackHole 2ch が入っているか |
| BlackHole が見つからない | インストール後に `sudo killall coreaudiod` で CoreAudio を再起動する |
| 自動録音で無音になる | マイクの許可を持つアプリ（Raycast など）から `scriba watch on` したか |
| ffmpeg が見つからない（Raycast から起動） | Raycast のスクリプトの `PATH` に ffmpeg の置き場があるか |
| Haas の処理に失敗する | `scriba setup-model` で準備を確認。`language = "ja"` を使い、残った音声は `scriba transcribe <id>` で再試行する |
| 会議名が付かない | `calendar_source` / `calendar_path` の設定、予定の開始が録音開始の ±10 分か。`scriba enrich latest` でやり直せる |
