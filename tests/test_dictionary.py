from scriba.transcription import dictionary


def test_load_mixed_terms(tmp_path):
    """terms に str と dict が混在してもロードできる。"""
    p = tmp_path / "dict.yaml"
    p.write_text(
        "terms:\n"
        "  - 山田\n"
        "  - word: GPT-Realtime\n"
        "    priority: high\n"
        "  - word: 低優先\n"
        "    priority: low\n",
        encoding="utf-8",
    )
    dic = dictionary.load(p)
    words = {t["word"] for t in dic.terms}
    assert words == {"山田", "GPT-Realtime", "低優先"}
    # str 指定は priority: high 扱い
    assert next(t for t in dic.terms if t["word"] == "山田")["priority"] == "high"


def test_load_empty_file(tmp_path):
    p = tmp_path / "dict.yaml"
    p.write_text("", encoding="utf-8")
    dic = dictionary.load(p)
    assert dic.terms == []
    assert dic.replacements == {}


def test_load_missing_file(tmp_path):
    dic = dictionary.load(tmp_path / "nope.yaml")
    assert dic.terms == []
    assert dic.replacements == {}


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "dict.yaml"
    src = dictionary.Dictionary(
        terms=[{"word": "山田", "priority": "high"}],
        replacements={"誤": "正"},
    )
    dictionary.save(p, src)
    loaded = dictionary.load(p)
    assert loaded.terms == [{"word": "山田", "priority": "high"}]
    assert loaded.replacements == {"誤": "正"}


def test_from_payload_strips_empty():
    payload = {
        "terms": [{"word": "A"}, {"word": "  "}, {"word": ""}, "B"],
        "replacements": [
            {"from": "x", "to": "y"},
            {"from": "  ", "to": "z"},  # from が空 → 除去
            {"from": "w", "to": ""},   # to は空でも残す
        ],
    }
    dic = dictionary.from_payload(payload)
    assert {t["word"] for t in dic.terms} == {"A", "B"}
    assert dic.replacements == {"x": "y", "w": ""}


def test_filters_roundtrip(tmp_path):
    """filters の save/load ラウンドトリップ。"""
    p = tmp_path / "dict.yaml"
    src = dictionary.Dictionary(filters=["了解です", "なるほど"])
    dictionary.save(p, src)
    loaded = dictionary.load(p)
    assert loaded.filters == ["了解です", "なるほど"]


def test_from_payload_filters_strips_empty():
    """from_payload は filters の空要素を除去する。"""
    payload = {
        "filters": [{"value": "A"}, {"value": "  "}, {"value": ""}, "B"],
    }
    dic = dictionary.from_payload(payload)
    assert dic.filters == ["A", "B"]


def test_effective_filters_union():
    """DEFAULT_FILTERS と dict.yaml filters の和集合（正規化・重複除去）。"""
    dic = dictionary.Dictionary(filters=["了解です", "はい。"])  # 「はい」はデフォルトと重複
    eff = dic.effective_filters()
    assert "了解です" in eff
    assert "はい" in eff
    assert all(d in eff for d in map(dictionary.normalize_filter, dictionary.DEFAULT_FILTERS))


def test_validate_prompt_char_fallback(monkeypatch):
    """トークナイザ非導入時の文字数フォールバック（warn/block 境界）。"""
    monkeypatch.setattr(dictionary, "_count_tokens", lambda p: None)

    # 空は ok
    assert dictionary.validate_prompt("")[0] == "ok"
    # CHAR_WARN=120 以下は ok
    assert dictionary.validate_prompt("あ" * dictionary.CHAR_WARN)[0] == "ok"
    # 120 超 150 以下は warn
    assert dictionary.validate_prompt("あ" * (dictionary.CHAR_WARN + 1))[0] == "warn"
    assert dictionary.validate_prompt("あ" * dictionary.CHAR_BLOCK)[0] == "warn"
    # 150 超は block
    assert dictionary.validate_prompt("あ" * (dictionary.CHAR_BLOCK + 1))[0] == "block"


def test_build_prompt_high_only():
    dic = dictionary.Dictionary(terms=[
        {"word": "A", "priority": "high"},
        {"word": "B", "priority": "low"},
    ])
    assert dic.build_prompt() == "会議の用語: A"


def test_truncated_clause_requires_repetition():
    """末尾の切れ端は、同じセグメントで直前に出た句の切れ端のときだけ定型とみなす。"""
    dic = dictionary.Dictionary()
    assert dic.is_filtered("このように、このように、この")
    assert not dic.is_filtered("はい、次回。")
    assert not dic.is_filtered("はい、私は")
