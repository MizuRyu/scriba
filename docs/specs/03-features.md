# 03 Features

## F1: 録音制御

### 概要
オンライン会議（Teams など）の音声を**2トラック**でチャンク録音する。1つの録音プロセス（sounddevice）で同時録音。

| トラック | 入力デバイス | 内容 | 話者ラベル |
|---|---|---|---|
| system | BlackHole 2ch | 相手（会議参加者）の声 | `[相手]` |
| mic | 外部マイク | 自分の声 | `[自分]` |

ヘッドフォン利用前提（スピーカー運用だとmicトラックに相手の声が混入する）。

旧バージョンは system トラックを `teams` と呼んでいた（`teams_000.wav` など）。読み込み・マージ・トラックフィルタは両方の名前を system として扱う。

### 操作
- `scriba start` — 録音開始。録音プロセスをバックグラウンドで起動
- `scriba stop` — 録音停止。録音プロセスに書き込み中のチャンクを確定させてから止める
- `scriba status` — 現在の状態（録音中/停止中、経過時間、チャンク数）
- `scriba discard [session]` — セッションを丸ごと破棄（誤録音対策）。録音中に実行すると録音を中止して破棄。ID省略時は最新セッション。TTYでは確認プロンプト、`-y`でスキップ

### 空セッションの扱い
- stop時に1チャンクも録れていなければ保存せず破棄し、「音声が録音できませんでした」と通知
- stop時に録音が `min_keep_sec`（既定 60 秒、0 で無効）より短ければ、文字起こしせず破棄する。手動・自動、止め方を問わない（待機画面だけの録音や、誤って入った会議の録音を残さない）
- 録音プロセスの起動失敗時も作りかけのセッションディレクトリを残さない

### start時のオーディオ設定バリデーション + 自動切替

複数出力装置は仮想デバイスのため、macOS標準のイヤフォン抜き差しフォールバック（物理デバイスの出現・消滅に反応するOS挙動）が効かない。よって普段は物理デバイスを出力にしておき、**録音中だけ複数出力装置に切り替える**。

start時のチェック項目:

- [ ] 出力が「複数出力装置」になっている — 未設定なら `switchaudio-osx` で自動切替し、stop時に元へ復元
- [ ] 複数出力装置のメンバーに BlackHole 2ch が含まれている
- [ ] 入力デバイスが BlackHole になっていない（なっていると会議アプリに自分の声が届かない）
- [ ] （警告のみ）複数出力装置の「音ずれ補正」がBlackHole側でON — 長時間録音のズレ防止

```bash
PREV=$(SwitchAudioSource -c)
SwitchAudioSource -s "複数出力装置"
trap 'SwitchAudioSource -s "$PREV"' EXIT
```

### Raycast連携
- Raycast Script Commandとして登録
- トグル動作: 録音中ならstop、停止中ならstart
- 通知: 開始/停止時にmacOS通知を出す

### 設定項目
- `device_system`: システム音声デバイス名（デフォルト: `BlackHole 2ch`）
- `device_mic`: マイクデバイス名（デフォルト: `外部マイク`）
- `chunk_duration`: チャンク長（秒）（デフォルト: `120`）
- `sample_rate`: サンプリングレート（デフォルト: `16000`）
- `multi_output_device`: 録音時に切り替える出力装置名（デフォルト: `複数出力装置`）

---

## F2: 文字起こし

### 概要
録音されたチャンクをmlx-whisperで文字起こしする。2つの動作モードを持つ。

### モード

| モード | 動作 | トラック | start時の指定 |
|---|---|---|---|
| **live**（デフォルト） | 録音中に逐次文字起こし | system（`capture_mic=true`でmicも併録） | `scriba start` or `scriba start --mode live` |
| **record-only** | 録音のみ。stop後にまとめて文字起こし | systemのみ | `scriba start --mode record-only` |

### 録音エンジンとマイク併録の制約
2026-07-02のlive実会議でsystemトラックが-48〜-91dB（数チャンクは完全無音）になる
事象が発生した。短時間のトーンテストでは2ストリーム同時でも劣化は再現しておらず、
原因は未確定。有力仮説は**Teamsクライアントのスピーカー設定**（Teamsはシステム既定
ではなくアプリ内設定のデバイスへ直接出力するため、そこが物理デバイスだとBlackHole
に届かない）。運用要件: Teamsの設定 > デバイス > スピーカーを「複数出力装置」にする。

既定はsystem単一ストリーム（実証済みで単純）。`capture_mic=true` で[自分]/[相手]
分離を有効化できる。無音チャンクを検知したら即通知する安全弁を持つ（下記）。

### 無音検知（安全弁）
録音プロセスがチャンク確定時にピーク振幅を確認し、無音（ルーティング断の疑い）なら
macOS通知で「会議アプリのスピーカーが複数出力装置か確認」と即警告する。通知はセッションごとに1回。

### liveモード
- startと同時にワーカーも起動
- 完成したチャンク（書き込み完了）を検出して文字起こし
- system/micの両トラックを別々に文字起こしし、認識 JSON のセグメントタイムスタンプで時刻順にマージ → `[自分]`/`[相手]` ラベル付きの `combined.txt` を生成
- Whisper 使用時は120秒チャンクの末尾ループ対策として `--condition-on-previous-text False` を指定（改善しなければチャンク長を60〜90秒に短縮）

### record-onlyモード
- 録音のみ実行。文字起こしワーカーは起動しない
- stop後に `scriba transcribe {session}` で手動実行
- または stop時に自動でバッチ文字起こしを走らせるオプション（`--transcribe-on-stop`）

### 後から文字起こし
- `scriba transcribe {session}` — 指定セッションの未処理チャンクを一括文字起こし
- `scriba transcribe --all` — 全未処理セッションを一括処理
- 既に文字起こし済みのチャンクはスキップ

### 設定項目
- `mode`: デフォルトモード（デフォルト: `live`）
- `model`: 認識モデル（デフォルト: `haas-ja-v1.0:q4_k`）。`haas-` で始まる名前は speech.cpp、それ以外は従来の mlx-whisper に渡す
- `language`: 言語（デフォルト: `ja`）
- `transcribe_on_stop`: record-onlyモードでstop時に自動文字起こし（デフォルト: `true`）
- `capture_mic`: liveでマイクも併録し[自分]/[相手]を分離（デフォルト: `false`。上記の制約に注意）

---

## F3: 保存先・ファイル名管理

### 概要
録音・文字起こし結果の保存先とファイル名フォーマットを設定で制御する。

### 設定項目
- `base_dir`: 保存先ルート（デフォルト: `~/scriba`）
- `session_format`: セッションディレクトリ名のフォーマット
  - `yyyymmdd-HHmmss` → `20260629-143000`
  - `yymmdd-HHmmss` → `260629-143000`
  - strftime形式で自由指定

---

## F4: 自動クリーンアップ

### 概要
指定日数を超えた録音ファイル（WAV）を自動削除する。文字起こし結果（txt）は保持。

### 設定項目
- `retention_days`: 保持日数（デフォルト: `7`）
- `cleanup_target`: 削除対象（デフォルト: `chunks`） — `chunks`（WAVのみ）, `all`（セッション丸ごと）

### 実行方式
`scriba start` 時に自動実行 + 手動の `scriba cleanup`。常駐デーモンは持たない。

### 安全弁
未文字起こしのチャンクが残るセッションは保持期間を過ぎても削除しない
（音声が失われるため）。スキップ時に `scriba transcribe` を案内する。

---

## F5: パフォーマンスログ

### 概要
文字起こし処理のパフォーマンスをJSONL形式で記録する。

### ログ項目
```jsonl
{
  "timestamp": "2026-06-29T14:32:00",
  "session": "20260629-143000",
  "chunk": "chunk_003",
  "audio_duration_sec": 120.0,
  "process_time_sec": 5.8,
  "rtf": 0.048,
  "model": "mlx-community/whisper-large-v3-turbo",
  "model_params": "809M",
  "text_length": 342
}
```

### 蓄積先
`{base_dir}/logs/performance.jsonl` — 全セッション共通で追記

---

## F6: HTMLビューア

### 概要
文字起こし結果とパフォーマンスログを閲覧する静的HTMLページ。

### デザイン
- 白黒シンプル（モノクロ基調）
- localhostサーバー不要（file://で直接開く）

### 画面構成

#### セッション一覧
- セッション名、日時、チャンク数、合計テキスト長
- クリックで詳細へ

#### セッション詳細
- 文字起こしテキスト全文（combined.txt の内容）
- チャンクごとのタイムスタンプ表示
- Discardボタン: 静的HTMLから直接削除はできないため、`scriba discard <id> -y` をクリップボードにコピーして案内する

#### パフォーマンスダッシュボード
- 処理時間の推移グラフ（Chart.js or 素のSVG）
- RTF（Real Time Factor）の推移
- セッション別・チャンク別の統計

### ナビゲーション
画面状態は location.hash（`#sessions` / `#performance` / `#dictionary` /
`#session=<id>`）で管理し、ブラウザの戻る/進むで一覧⇄詳細⇄タブを行き来できる。

### データ読み込み方式
両方式を実装。

1. `scriba view`（デフォルト）: データ埋め込みの静的HTML生成。実行時点のスナップショット
2. `scriba view --serve [--port 8737]`: 簡易HTTPサーバー。5秒ごとに自動更新（liveモード中に文字起こしが伸びるのが見える）、Discardボタンがワンクリック削除になる。Ctrl+Cで停止

### サーバーの自動停止（消し忘れ対策）
serveモードは起動から `serve_timeout_min`（デフォルト180分）で自動停止し、macOS通知を出す。`0` で無効化。

---

## F7: 辞書機能（固有名詞の誤変換対策）

### 概要
辞書ファイル1つ（`dict.yaml`）を2つの用途に使い、固有名詞の誤変換を減らす。

1. **認識側**: `priority: high` の頻出語を Haas の `--keywords`、または mlx-whisper の `--initial-prompt` に渡す。Haas は `Haas=ハース` のような読みも扱う
2. **修正側**: 誤変換パターンの置換辞書（`誤: 正` 形式）で文字起こし後に一括置換。件数上限なし

### 辞書フォーマット（案）

```yaml
terms:                # initial-prompt に入れる用語（priority: high のみ）
  - word: GPT-Realtime
    priority: high
  - word: 単体テスト
    priority: high
replacements:         # 文字起こし後の置換
  設計ショー: 設計書
  設計ショー: 設計書
```

Haas は Silero VAD で最大12秒の発話区間に分ける。用語ヒントと認識時刻は speech.cpp 0.10.0 では併用できないため、用語ありでは発話区間の時刻を保存する。用語なしでは `--timestamps` の認識時刻を保存する。`scriba setup-model` で実行ファイルと重みを事前取得できる。

停止後に処理できないチャンクが残ったワーカーは終了する。stop は完了通知と自動転送をせず、元音声を残して `scriba transcribe` を案内する。

### Whisper の initial-prompt のバリデーション（上限224トークン）

- **UI/CLI側（簡易）**: 文字数ベース。日本語は1文字≒1〜2トークンのため、120文字超で警告、150文字で登録ブロック
- **保存時（正確）**: Whisperトークナイザで実測

```python
from mlx_whisper.tokenizer import get_tokenizer
tok = get_tokenizer(multilingual=True, language="ja", task="transcribe")
assert len(tok.encode(prompt_text)) <= 224
```

### 設定項目
- `dict_path`: 辞書ファイルパス（デフォルト: `{base_dir}/dict.yaml`）

### フィルタ（非重要発話の除去）
dict.yaml の `filters:` に登録した文言と完全一致するセグメントを combined.txt
生成時に除去する（`filters_enabled = false` で無効化）。一致判定は前後空白と
末尾句読点を正規化したセグメント単位の完全一致のみ（部分一致は誤爆するため禁止）。
内蔵デフォルト: Whisper幻聴定型（「ご視聴ありがとうございました」等）と単独の「はい」。
内蔵デフォルトは編集UIに読み取り専用で表示し、ユーザー登録分との和集合で除去する。
combined.txt は1本のみでフィルタ適用済みを正とする。生データは transcripts/*.json が
担っており、`scriba merge` でいつでも再生成できる。

加えて**連続重複の畳み込み**を常時行う: 正規化後テキストが時系列で連続一致する
セグメント（挨拶の反復、2トラックのエコー等）は最初の1つだけ残す。
非連続の同一発話は畳まない。

### combined.txt の再生成・会議名
- `scriba merge <session> [--until <分>]` — 既存JSONから combined.txt を再生成。
  辞書・フィルタの現内容を再適用。`--until 55` で55分以降のセグメントを除外
  （録りすぎた末尾の切り落とし用）
- `scriba title <session|latest> <会議名>` — 予定外の会議に後から名前を付ける。
  meta.json の `title` に保存し、ビューアの一覧・詳細に表示

### 編集UI
`scriba view --serve` のDictionaryタブで用語・置換ルール・フィルタをGUI編集して
保存できる（サーバー経由で dict.yaml に書き込み）。静的HTMLでは編集不可のため案内を表示。
用語の文字数はUIで概算警告し、保存時にサーバーが正確なトークン判定を返す。
CLIからは `scriba dict show` / `scriba dict validate`。

### 同一フレーズ連続trim
Whisper幻聴で発生する同一フレーズの異常連続（「いけないといけないといけない...」）を
正規表現で検知し、最初の1回だけ残す。`merge_session()` 内で置換辞書適用の直後に実行。

---

## F8: カレンダー照合・メタ情報付加（enrich）

### 概要
予定表から会議タイトル・案件・組織を推定し、文字起こしファイルの frontmatter に付加する。後続の処理が推測なしで扱える状態をつくる。詳細は [06](06-calendar-enrich.md)。

### 予定データの取得
取得元はアダプタで選ぶ（`calendar_source`）。`json`（外部が書き出したイベント形式のファイル）と `ics`（.ics ファイルまたは iCal URL）。

### 照合ロジック
- `scriba start` 時刻と予定の開始時刻を比較（±10分以内）
- 一意マッチ → 自動でタイトル設定
- 同時刻に複数 → サジェスト表示
- マッチなし → タイトル空（後から `scriba title` で設定）

### メタ情報抽出（決定論的・LLM不使用）
1. **組織推定**: organizer のメールドメイン → `config.toml` の `[enrich.organizations]` マッピング
2. **プロジェクト推定**: subject のキーワード → `config.toml` の `[[enrich.projects]]` マッピング（順序重要）
3. **仕訳ルール学習**: export 時に分類を `classification_rules.jsonl` に記録。次回同タイトルの定例は自動分類

### frontmatter
combined.txt の先頭に YAML frontmatter を付加:
```yaml
---
title: "【ACME】定例"
date: 2026-07-06
start: "09:15"
end: "10:00"
organization: ACME
project: acme
source_session: 20260706-091500
---
```

### 操作
- `scriba enrich <session>` — カレンダー照合・メタ情報付加を再実行

### 設定
`config.toml` の `calendar_source` / `calendar_path` で取得元を、`[enrich]` セクションで組織マッピング・プロジェクトマッピングを定義。`scriba view --serve` の Settings タブからGUI編集可能。

---

## F9: transcript の転送（export）

### 概要
プロジェクト分類済みの transcript を `{export_dir}/{export_subdir}`（既定 `transcript/{project}/`）にコピーする。`export_dir` が未設定なら転送せず、未転送の通知もしない。

### ルール
- プロジェクト確定済み → 転送先にコピー
- 内部MTGは `internal` プロジェクトとして扱う（config.toml で「（内部）」「社内」等のキーワードマッチ。客先名を含むタイトルは客先プロジェクト優先のため internal は最後に定義）
- 未分類 → export しない（ユーザーが手動で分類してから）
- 二重転送防止: meta.json の `exported_at` で管理
- `scriba stop` 時にタイトル＋enrich が確定していれば自動実行

### 操作
- `scriba export [session]` — 手動転送（session省略で全未転送）
- `scriba view --serve` の詳細画面から「転送」ボタンで操作可能
- 転送先プロジェクトはドロップダウンで選択。確定済みprojectはプリセレクト

### 設定
- `export_dir`: 転送先ルート（デフォルト: 空 = 転送しない）
- `export_subdir`: 転送先ルート配下のフォルダ。`{project}` が案件名に置き換わる（デフォルト: `transcript/{project}`）

---

## F10: 録音タイムアウト

### 概要
切り忘れ対策として、録音開始から一定時間で自動停止する。

### 動作
- デフォルト: 180分（3時間）で強制停止
- macOS通知: 「録音がXX分でタイムアウトしました。切り忘れの可能性があります。」
- meta.json に `stopped_reason: "timeout"` を記録
- **タイムアウト停止の場合、enrich/export は自動実行しない**（確認後に手動で実行）
- 文字起こしは実行される

### 設定
- `max_recording_min`: タイムアウト分数（デフォルト: `180`）

---

## F11: トラックフィルタ

### 概要
2トラック録音（system + mic）のセッションで、特定トラックのみでcombined.txtを再生成する。自分が一言も喋らなかった会議で mic トラックのノイズを除去する用途。

### 操作
- CLI: `scriba merge <session> --track system` （system/mic/both。旧名 teams も可）
- `scriba view --serve` の詳細画面で「相手のみ」「自分のみ」「両方」ボタン
- フィルタ状態は meta.json の `track_filter` に保存
- そのフィルタ状態で export される

---

## F12: 自動録音（watch）

### 概要
会議アプリがマイクを使い始めたら録音を始め、使わなくなったら止める常駐プロセス。

### 動作
- 会議アプリは `meeting_apps`（bundle id の接頭辞。既定 `["com.microsoft.teams"]`）で指定する。macOS 14.2 以降の CoreAudio のプロセス情報から、そのアプリがマイク入力を使っているかを 2 秒ごとに見る
- マイク使用が約4秒続いたら `scriba start`、不使用が約10秒続いたら、その会議で録っていたセッションを `scriba stop`（`stopped_reason: meeting_end`）
- 参加前の待機画面でもアプリはマイクを開く。待機だけで終わった短い録音は stop が破棄する（F1「空セッションの扱い」）
- 会議中に手で止めた録音は、その会議では再開しない。連続した会議は会議ごとに別セッションになる

### 操作
- `scriba watch on | off | toggle`。`scriba status` の1行目に有効/無効を出す
- 録音プロセスはマイクの許可を起動元から受け継ぐ。マイクの許可を持つアプリ（Raycast など）から有効にする
- ログ: `{base_dir}/logs/watch.log`

### 設定
- `meeting_apps`: 会議中とみなすアプリ（例: Zoom を加えるなら `["com.microsoft.teams", "us.zoom.xos"]`）
