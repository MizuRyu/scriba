# 04 Workflow

## ワークフロー: liveモード（デフォルト）

```
会議開始
  │
  ▼
[1] Raycast ショートカット or `scriba start`
  │  ├─ オーディオ設定バリデーション（出力/入力デバイス、詳細は03 F1）
  │  ├─ 出力を複数出力装置に自動切替（元の出力を記憶）
  │  ├─ セッションディレクトリ作成
  │  ├─ 録音プロセス開始（system/mic 2トラック、バックグラウンド）
  │  └─ 文字起こしワーカー開始（バックグラウンド）
  │
  ▼
[2] 録音中（自動処理）
  │  ├─ 録音プロセス: 2分ごとにチャンクWAV生成（system_*/mic_*）
  │  ├─ ワーカー: 完成チャンクを検出 → mlx-whisper実行（辞書のinitial-prompt付き）
  │  ├─ ワーカー: 両トラックをタイムスタンプでマージ + 置換辞書適用 → combined.txt更新
  │  └─ ワーカー: performance.jsonlにログ追記
  │
  ▼
[3] 会議終了 → Raycast ショートカット or `scriba stop`
  │  ├─ 録音プロセス停止
  │  ├─ 出力デバイスを元に復元
  │  ├─ 最後のチャンクを文字起こし
  │  ├─ combined.txt 最終更新
  │  └─ macOS通知「文字起こし完了」
  │
  ▼
[4] 結果確認
     └─ `scriba view` or HTMLを直接開く
```

## ワークフロー: record-onlyモード

```
会議開始
  │
  ▼
[1] `scriba start --mode record-only`
  │  ├─ セッションディレクトリ作成
  │  └─ 録音プロセス開始（バックグラウンド）のみ
  │
  ▼
[2] 録音中
  │  └─ 録音プロセス: 2分ごとにチャンクWAV生成（文字起こしは走らない）
  │
  ▼
[3] 会議終了 → `scriba stop`
  │  ├─ 録音プロセス停止
  │  ├─ transcribe_on_stop=true なら自動でバッチ文字起こし開始
  │  └─ macOS通知「録音停止（文字起こし処理中...）」
  │
  ▼
[4] バッチ文字起こし（自動 or 手動）
  │  ├─ 自動: stop時に全チャンクを一括処理
  │  └─ 手動: `scriba transcribe {session}`
  │
  ▼
[5] 結果確認
     └─ `scriba view` or HTMLを直接開く
```

## Raycast Script Command

```bash
#!/bin/bash
# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Toggle Meeting Transcription
# @raycast.mode silent

# トグル動作
if scriba status --quiet; then
  scriba stop
  echo "録音停止"
else
  scriba start
  echo "録音開始"
fi
```

## エラーケース

| ケース | 動作 |
|---|---|
| BlackHoleが認識されない | エラーメッセージ + 利用可能なデバイス一覧を表示 |
| 入力デバイスがBlackHole | エラーで起動中止（会議アプリに自分の声が届かない状態） |
| 複数出力装置にBlackHoleが未登録 | エラーメッセージ + Audio MIDI設定の手順を案内 |
| マイクデバイスが見つからない | 警告してsystemトラックのみで録音続行（自分の声なし） |
| 録音中にstart | 「既に録音中です」と通知。二重起動しない |
| 録音プロセスのクラッシュ | ワーカーが検出して通知。PIDファイル削除 + 出力デバイス復元 |
| ディスク容量不足 | TBD |
| mlx-whisper失敗 | 該当チャンクをスキップしてログに記録。次のチャンクは継続 |
| 辞書のinitial-promptが224トークン超 | 保存時にブロック（F7のバリデーション） |

## 日次メンテナンス

```
毎日 or start時
  │
  ▼
retention_days を超えたセッションの chunks/ を削除
  │
  ▼
削除ログを出力
```
