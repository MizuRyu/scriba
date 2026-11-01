# Teams会議リアルタイム文字起こし — 技術検討

作成: 2026-06-29

当初の技術検討の記録。録音エンジンはのちに ffmpeg から sounddevice に替えた（[ADR-002](../adr/002-sounddevice-capture.md)）。

## 要件

- Teams会議中の音声を録音し、逐次的に文字起こしする
- リアルタイムストリーミングは不要。チャンク単位の逐次処理でOK
- **品質重視**（低レイテンシより高精度）
- macOS / Apple Silicon (M1 Max)
- ローカル完結

## 結論: 推奨構成

**BlackHole 2ch + ffmpeg（チャンク録音） + mlx-whisper（逐次文字起こし）**

既存の mlx-whisper + large-v3-turbo をそのまま活用。新たに必要なのは音声キャプチャ部分のみ。

## アーキテクチャ

```
Teams会議
  ↓ システム音声
BlackHole 2ch（仮想オーディオデバイス）
  ↓
ffmpeg -f avfoundation（チャンク録音: 例 2分ごと）
  ↓ chunk_000.wav, chunk_001.wav, ...
監視ループ（新規チャンク検出）
  ↓
mlx-whisper（文字起こし）
  ↓
transcript_000.txt, transcript_001.txt, ...
  ↓
結合・表示
```

## 段階的な実装計画

### Phase 1: 音声キャプチャ環境の構築

1. **BlackHole 2ch インストール**（Homebrew: `brew install blackhole-2ch`）
2. **Audio MIDI設定で複数出力装置を作成**: 内蔵スピーカー + BlackHole 2ch
3. macOSのサウンド出力を複数出力装置に変更
4. ffmpegでBlackHole経由の録音テスト

```bash
# デバイス一覧確認
ffmpeg -f avfoundation -list_devices true -i ""

# テスト録音（10秒）
ffmpeg -f avfoundation -i ":BlackHole 2ch" -t 10 -ac 1 -ar 16000 test.wav
```

### Phase 2: チャンク録音スクリプト

ffmpegの `-f segment` でN秒ごとにファイル分割しながら連続録音。

```bash
ffmpeg -f avfoundation -i ":BlackHole 2ch" \
  -ac 1 -ar 16000 -c:a pcm_s16le \
  -f segment -segment_time 120 -reset_timestamps 1 \
  "chunks/chunk_%03d.wav"
```

- 16kHz mono WAV: Whisperの入力フォーマットに最適
- 2分（120秒）チャンク: 品質と遅延のバランス良好
- チャンク長は調整可能（30秒〜5分）

### Phase 3: 逐次文字起こしスクリプト

新規チャンクを検出したら mlx-whisper で文字起こし。

```bash
# 監視ループ（概念）
inotifywait / fswatch で chunks/ を監視
  → 新規 .wav 検出
  → mlx-whisper で文字起こし
  → 結果を transcripts/ に出力
  → 全結合テキストを更新
```

### Phase 4: 統合（起動/停止をワンコマンドに）

- 録音プロセスと監視プロセスをまとめて起動
- Ctrl+C で両方停止
- 最終結合テキストを出力

## 技術的な判断

### チャンク長の選択

| チャンク長 | 遅延 | 品質 | 備考 |
|---|---|---|---|
| 30秒 | 短い | やや低い | 文脈が短く精度が下がりやすい |
| 60秒 | 中程度 | 良好 | バランス型 |
| **120秒** | **2分** | **最良** | **推奨。Whisperは長い文脈で精度向上** |
| 300秒 | 5分 | 最良 | 遅延が大きすぎる可能性 |

### なぜリアルタイムストリーミングを採用しないか

- whisper.cppのストリーミングモードは短いウィンドウで推論 → 文脈不足で品質低下
- mlx-whisper + large-v3-turbo はチャンク一括処理で最高精度
- 2分チャンクなら M1 Max で10-20秒で処理完了 → 実質的に十分な速度

### マイク音声（自分の声）の扱い

| 方式 | 利点 | 欠点 |
|---|---|---|
| システム音声のみ | シンプル | 自分の声が入らない |
| マイク+システム音声を合成 | 全参加者の声が入る | エコー・ハウリングの可能性 |
| 別トラックで同時録音 | 話者分離しやすい | 合成処理が必要 |

初期実装は**システム音声のみ**で開始し、必要に応じてマイク追加。

## 既存OSSとの比較（自作の理由）

| ツール | 問題点 |
|---|---|
| Buzz (19.9k★) | GUIアプリ。CLI制御・チャンク逐次処理に不向き |
| WhisperLive | NVIDIA GPU前提のサーバー構成。macOSローカル不向き |
| whisper_streaming (UFAL) | ストリーミング特化。品質重視のチャンク処理とは方向性が違う |

自作のほうが要件にフィット: シンプルなシェルスクリプト、既存mlx-whisper活用、チャンク品質最優先。

## 必要なもの

- mlx-whisper
- BlackHole 2ch（インストール後に認識されなければ coreaudiod を再起動）
- ffmpeg
- fswatch（チャンク監視用。のちにポーリングに置き換えたため不要）

## 実測結果（2026-06-29）

### 音声キャプチャ

- BlackHole 2ch + 複数出力装置でTeams会議音声のキャプチャに成功
- macOSサウンド出力を「複数出力装置」に切り替える必要あり
- coreaudiod再起動（`sudo kill $(pgrep coreaudiod)`）後にCLIから認識される
- Microsoft Teams Audioデバイスは直接録音しても無音（Teams内部ルーティング専用）

### 文字起こし性能

| 音声長 | 処理時間 | 倍速 |
|---|---|---|
| 30秒 | 4秒 | 7.5x |
| 60秒 | 5秒 | 12x |
| 120秒 | 6秒 | 20x |

品質: 会議内容は十分読める。議事録の下書きとして実用的。固有名詞の誤変換あり。

### 話者分離（検討のみ・未実施）

- pyannote/speaker-diarization-3.1 が有力候補
- 公式DER: AMI会議音声で18.8%、モノラル混合だと20-30%程度の見込み
- モデルの利用には HuggingFace 上で利用条件への同意が必要
- 代替案: 必要になれば試行する。会議アプリ自体の文字起こし機能も候補
- → 2トラック録音（下記）を採用したため「自分 vs 相手」の分離には不要になった

## 追加仕様（2026-07-02）

2トラック録音・辞書機能・録音ON時のオーディオバリデーション等を検討し、docs/specs/ に反映済み。詳細はそちらを参照。
