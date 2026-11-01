# 05 Model Selection

## 現行モデル

既定は **Haas-ja-v1.0 Q4_K**（`haas-ja-v1.0:q4_k`）。speech.cpp 0.10.0 の Metal 版を別プロセスで実行する。日本語専用。実行ファイルは SHA256 を検証し、重みは同版のカタログが固定したリビジョンと SHA256 で取得する。認識結果は既存の `text` / `segments` 形式で保存し、旧 Whisper セッションも読める。判断と制約は [ADR-006](../adr/006-haas-default.md)。

Haas の長い音声は Silero VAD で最大12秒の発話区間に分ける。用語ヒントを使う場合は区間の時刻、使わない場合は認識のセグメント時刻を保存する。

`model = "mlx-community/whisper-large-v3-turbo"` など従来のモデル名を設定すれば mlx-whisper を使う。

## 旧モデルの調査と採用記録

調査日: 2026-06-30

## 日本語ASRモデル CER比較

| モデル | パラメータ | CommonVoice 8 ja | JSUT Basic 5000 | ReazonSpeech | 備考 |
|---|---|---:|---:|---:|---|
| whisper-large-v3 | 1,550M | 8.5% | 7.1% | 14.9% | 最高精度。重い |
| whisper-large-v2 | 1,550M | 9.7% | 8.2% | 28.1% | 旧世代 |
| **whisper-large-v3-turbo** | **809M** | **≈9%** | **—** | **—** | **採用中。公式CER未公表、v3比+0.3〜0.7pt程度の劣化推定** |
| kotoba-whisper-v2.0 | 756M | 9.2% | 8.4% | 11.6% | 日本語特化。ReazonSpeechで最良 |

※ CER = Character Error Rate（低いほど良い）

## 速度比較

| モデル | パラメータ | large-v3比の速度 | M1 Maxでの実測（120秒音声） |
|---|---|---|---|
| whisper-large-v3 | 1,550M | 1x（基準） | 未計測 |
| whisper-large-v3-turbo | 809M | 5〜8x | **6秒（20x実時間）** |
| kotoba-whisper-v2.0 | 756M | ≈6.3x | 未計測 |

large-v3-turboはデコーダを32層→4層に削減。エンコーダはlarge-v3と同一。

## 採用モデル

**mlx-community/whisper-large-v3-mlx**（2026-07-10 に turbo から切替）

### 切替理由（2026-07-10 実測）

- M1 Max実測: 120秒チャンク→11秒（11x実時間）。turbo（6秒）比で約1.8倍遅いだけで、当初推定の5〜8倍より大幅に軽い
- CERで0.5〜1pt改善見込み（8.5% vs turbo推定9%）
- liveモード（120秒間隔）に対し11秒処理で余裕。record-only一括も2時間会議で11分程度
- 注意: MLXのリポジトリ名は `whisper-large-v3-mlx`（`-mlx`サフィックス必須。`whisper-large-v3` は存在しない）

### 旧採用モデル: mlx-community/whisper-large-v3-turbo

- M1 MaxのMetal GPUで20x実時間速度（120秒→6秒）。会議中の逐次処理に十分
- 日本語CERは推定9%前後。議事録下書きとしては十分な精度
- 速度最優先に戻す場合はこちら

### 代替候補（将来検討）

| モデル | 検討理由 |
|---|---|
| whisper-large-v3 | 精度重視の場合。turbo比でCER 0.5〜1pt改善が見込めるが、処理速度は5〜8倍遅い |
| kotoba-whisper-v2.0 | 日本語特化。ReazonSpeechベンチで最良。mlx版の有無を要確認 |
| whisper-large-v3-turbo-q8 | メモリ節約。精度劣化の度合いを要検証 |

### 精度改善の方向性（将来）

- **プロンプト調整**: `--initial-prompt` に会議の文脈語（プロジェクト名、固有名詞）を渡すことでCER改善の可能性
- **後処理**: 固有名詞辞書による置換（「設計ショー」→「設計書」等）
- **VAD（音声活動検出）**: 無音区間を除外してWhisperのハルシネーションを抑制

## ベンチマーク環境の補足

- Open ASR Leaderboard (HuggingFace): 日本語専用トラックは未設置（英語+欧州5言語のみ）
- 日本語ASRの横断比較は [japanese-asr](https://huggingface.co/japanese-asr) コミュニティが独自実施
- 上記CER値はモデルカード・コミュニティベンチからの引用。条件（正規化、句読点除去等）が統一されていない点に注意
