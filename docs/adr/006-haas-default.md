# ADR-006 Haas Q4_K を既定の音声認識モデルにする

- 状態: 承認
- 日付: 2026-11-01
- 関連: [モデル選定](../specs/05-model-selection.md)、[ADR-003](003-heavy-deps-in-subprocess.md)

## 文脈

日本語の会議を端末内で文字起こしし、既存の2トラックのマージ、辞書、予定照合、転送を保つ。Haas-ja-v1.0 は speech.cpp の軽量な実行ファイルから使え、Python 本体に機械学習の依存を追加せずに済む。

## 決定

- 既定を `haas-ja-v1.0:q4_k` にする。`haas-` で始まるモデル名は speech.cpp、それ以外は従来の mlx-whisper に渡す。既存設定のモデル名は書き換えない。
- speech.cpp 0.10.0 の macOS arm64 Metal 版を初回取得し、アーカイブと実行ファイル・共有ライブラリの SHA256 を検証する。重みは同版のカタログが固定したリビジョンと SHA256 に従う。これは再現性と取得物の検証のための固定で、更新時はハッシュと実音声での検証も更新する。
- Silero VAD で発話を最大12秒の区間に分けて認識する。120秒の録音チャンクは変えない。長い発話を丸ごと渡すことによる認識の欠落を避ける。
- `priority: high` の用語を `keywords` に渡す。speech.cpp は `keywords` と `timestamps` を併用できないため、用語ありでは発話区間の開始・終了を保持する。用語なしでは認識結果のセグメント時刻を使う。区間の時刻を語単位の時刻とは扱わない。
- `text` / `segments` / `language` を持つ既存形式で保存し、`model` と `timestamp_source` を記録する。結果が不正・未完了ならチャンクを処理済みにせず、WAV を残す。
- モデルとランタイムは常駐させない。CLI と録音プロセスの依存を軽く保つ。

## 制約と見直し条件

- Haas は日本語専用。他言語には従来の Whisper を指定する。
- 用語ありの時刻は発話区間の粒度。speech.cpp が用語補正後の時刻に対応したら、`--keywords --timestamps` の組み合わせと2トラックのマージを実音声で確認して更新する。
- 発話の境界では単語が変わることがある。会議音声で欠落や認識精度の問題が確認されたら、同じ音声で区間長・モデルを比較する。音声入力での好評だけで会議全般の精度を保証しない。

## 一次情報

- [speech.cpp 0.10.0 の CLI](https://github.com/nyosegawa/speech.cpp/blob/v0.10.0/docs/cli.md)
- [Haas の用語ヒントと時刻の制約](https://github.com/nyosegawa/speech.cpp/blob/v0.10.0/docs/models/fastconformer.md#a-custom-vocabulary-haas)
- [Haas Q4_K の固定リビジョン](https://huggingface.co/sakasegawa/Haas-ja-v1.0-GGUF/tree/6b965d5007ba780585de51549d57a8c1c0d67c7e)
