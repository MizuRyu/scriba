"""F7: 辞書機能。initial-prompt用語（認識側）と置換辞書（修正側）とフィルタ（除去側）。

dict.yaml:
  terms:
    - word: GPT-Realtime
      priority: high
  replacements:
    設計ショー: 設計書
  filters:
    - ご視聴ありがとうございました
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROMPT_PREFIX = "会議の用語: "
TOKEN_LIMIT = 224
# 日本語は1文字≒1〜2トークンのため文字数で近似バリデーション
CHAR_WARN = 120
CHAR_BLOCK = 150

# 内蔵デフォルトフィルタ: Whisperの幻聴定型・単独の相槌。
# dict.yaml の filters と和集合で使う（編集UIには出さない）。
DEFAULT_FILTERS = [
    "ご視聴ありがとうございました",
    "次回予告",
    "次の動画でお会いしましょう",
    "チャンネル登録お願いします",
    "はい",
    # large-v3 が無音のmicトラックで出す定型（no_speech_prob 0.75前後、micにしか出ない）
    "私はあなたを愛しています",
    "私は彼らを愛しています",
    "彼らは私を見つけました",
    "私は彼らを見つけました",
    "私は、私の動画を撮影しています",
    "このように",
    "おやすみなさい",
    "音量を調整します",
    "早送り",
]

# 定型句の前置き。句の先頭から外してから照合する（「はい、では次の動画でお会いしましょう」）。
# 前置きだけの句は照合対象から外れるので、「では」単独の発話は残る
_FILLER_PREFIX = re.compile(r"^(それでは|では|じゃあ)")

# 一致判定の正規化で落とす末尾の句読点・記号
_FILTER_STRIP = "。、！？!?…"
_CLAUSE_SPLIT = re.compile(rf"[{re.escape(_FILTER_STRIP)}\s]+")


def normalize_filter(text: str) -> str:
    """フィルタ一致判定用の正規化: 前後空白と末尾の句読点・記号を除去。"""
    return re.sub(rf"[{re.escape(_FILTER_STRIP)}]+$", "", text.strip())


@dataclass
class Dictionary:
    terms: list[dict] = field(default_factory=list)
    replacements: dict[str, str] = field(default_factory=dict)
    filters: list[str] = field(default_factory=list)

    def effective_filters(self) -> set[str]:
        """DEFAULT_FILTERS と dict.yaml の filters の和集合（正規化済み・重複除去）。"""
        return {normalize_filter(f) for f in DEFAULT_FILTERS + self.filters if normalize_filter(f)}

    def is_filtered(self, text: str) -> bool:
        """セグメント全体か、句読点・空白で区切った全ての句（前置き除去後）がフィルタに一致すれば対象。

        句単位の完全一致なので、フィルタ語を含むだけの発話（「はい、承知しました」）は残る。
        """
        filters = self.effective_filters()
        if normalize_filter(text) in filters:
            return True
        clauses = [_FILLER_PREFIX.sub("", c) for c in _CLAUSE_SPLIT.split(text.strip())]
        clauses = [c for c in clauses if c]
        if not clauses or not all(c in filters for c in clauses[:-1]):
            return False
        last = clauses[-1]
        # Whisperの繰り返しループはセグメント末尾で語の途中で切れる（「このように、このように、この」）。
        # 直前までに出た句の切れ端に限る（「はい、次回」の「次回」は「次回予告」の切れ端ではない）
        truncated = len(last) >= 2 and any(c.startswith(last) for c in clauses[:-1])
        return last in filters or truncated

    def build_prompt(self, model: str = "") -> str:
        words = [t["word"] for t in self.terms if t.get("priority") == "high"]
        if not words:
            return ""
        if model.startswith("haas-"):
            return "\n".join(words)
        return PROMPT_PREFIX + "、".join(words)

    def apply_replacements(self, text: str) -> str:
        for wrong, right in self.replacements.items():
            text = text.replace(wrong, right)
        return text


def load(path: Path) -> Dictionary:
    if not path.exists():
        return Dictionary()
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    terms = []
    for t in raw.get("terms") or []:
        if isinstance(t, str):
            terms.append({"word": t, "priority": "high"})
        elif isinstance(t, dict) and t.get("word"):
            terms.append({"word": str(t["word"]), "priority": t.get("priority", "high")})
    replacements = {str(k): str(v) for k, v in (raw.get("replacements") or {}).items()}
    filters = [str(f) for f in (raw.get("filters") or []) if str(f).strip()]
    return Dictionary(terms=terms, replacements=replacements, filters=filters)


def save(path: Path, dic: Dictionary) -> None:
    data = {
        "terms": [{"word": t["word"], "priority": t.get("priority", "high")} for t in dic.terms],
        "replacements": dict(dic.replacements),
        "filters": list(dic.filters),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def from_payload(payload: dict) -> Dictionary:
    """HTML等から受け取ったJSONペイロードをDictionaryに変換（空要素は除去）。"""
    terms = []
    for t in payload.get("terms") or []:
        word = str((t.get("word") if isinstance(t, dict) else t) or "").strip()
        if word:
            terms.append({"word": word, "priority": "high"})
    replacements: dict[str, str] = {}
    for r in payload.get("replacements") or []:
        wrong = str(r.get("from", "")).strip()
        right = str(r.get("to", "")).strip()
        if wrong:
            replacements[wrong] = right
    filters = []
    for f in payload.get("filters") or []:
        val = str((f.get("value") if isinstance(f, dict) else f) or "").strip()
        if val:
            filters.append(val)
    return Dictionary(terms=terms, replacements=replacements, filters=filters)


def validate_prompt(prompt: str, model: str = "") -> tuple[str, str]:
    """(判定, メッセージ)。判定: ok | warn | block"""
    if model.startswith("haas-"):
        return "ok", f"Haas の認識ヒント: {len(prompt.splitlines())}語"
    n = len(prompt)
    if n == 0:
        return "ok", "initial-prompt なし（priority: high の用語が未登録）"
    exact = _count_tokens(prompt)
    if exact is not None:
        if exact > TOKEN_LIMIT:
            return "block", f"{exact}トークン（上限{TOKEN_LIMIT}超過）。priority: high の用語を減らしてください"
        return "ok", f"{exact}トークン / 上限{TOKEN_LIMIT}（{n}文字）"
    # トークナイザが使えない環境では文字数で近似
    if n > CHAR_BLOCK:
        return "block", f"{n}文字（{CHAR_BLOCK}文字超）。224トークンを超える可能性が高いため用語を減らしてください"
    if n > CHAR_WARN:
        return "warn", f"{n}文字（{CHAR_WARN}文字超）。上限224トークンに近づいています"
    return "ok", f"{n}文字（上限の目安{CHAR_WARN}文字以内）"


def _count_tokens(prompt: str) -> int | None:
    """Whisperトークナイザでの実測。mlx_whisperが未導入なら None。"""
    try:
        from mlx_whisper.tokenizer import get_tokenizer

        tok = get_tokenizer(multilingual=True, language="ja", task="transcribe")
        return len(tok.encode(prompt))
    except Exception:
        return None
