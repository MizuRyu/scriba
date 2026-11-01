from scriba.transcription import dictionary
from scriba.viewer import render as viewer


def test_dict_payload_includes_default_filters(cfg):
    """_dict_payload の戻り値に default_filters（DEFAULT_FILTERS）が含まれる。"""
    payload = viewer.dict_payload(cfg)
    assert payload["default_filters"] == list(dictionary.DEFAULT_FILTERS)


def test_haas_dictionary_uses_keywords_and_no_whisper_token_limit(cfg):
    dictionary.save(cfg.dictionary_path, dictionary.Dictionary(terms=[
        {"word": "Haas=ハース", "priority": "high"},
        {"word": "確認用語" * 40, "priority": "high"},
    ]))
    payload = viewer.dict_payload(cfg)
    assert payload["prompt"].startswith("Haas=ハース\n")
    assert payload["verdict"] == "ok"
    html = viewer.settings(cfg)
    assert 'data-engine="haas"' in html
    assert "224トークン" not in html


def test_saving_enrich_keeps_other_settings(tmp_path, monkeypatch):
    from scriba import config
    from scriba.viewer import server

    monkeypatch.setenv("SCRIBA_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        'meeting_apps = ["com.microsoft.teams", "us.zoom.xos"]\ncapture_mic = true\nchunk_duration = 60\n'
        'calendar_source = "ics"\n',
        encoding="utf-8",
    )
    cfg = config.load()
    server._save_enrich(cfg, {"organizations": {}, "projects": [{"alias": "acme", "keywords": ["ACME"]}]})

    reloaded = config.load()
    assert reloaded.meeting_apps == ["com.microsoft.teams", "us.zoom.xos"]
    assert reloaded.capture_mic is True
    assert reloaded.chunk_duration == 60
    assert reloaded.calendar_source == "ics"
    assert reloaded.enrich_projects == [{"alias": "acme", "keywords": ["ACME"]}]


def test_saving_enrich_keeps_dotted_domains(tmp_path, monkeypatch):
    from scriba import config
    from scriba.viewer import server

    monkeypatch.setenv("SCRIBA_HOME", str(tmp_path))
    cfg = config.load()
    orgs = {"acme.example": "ACME", "sales.acme.example": "ACME 営業", 'odd"key': "x"}
    server._save_enrich(cfg, {"organizations": orgs, "projects": []})

    assert config.load().enrich_organizations == orgs
