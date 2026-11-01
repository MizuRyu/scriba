from scriba import config
from scriba.config import Config


def test_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBA_HOME", str(tmp_path))
    cfg = config.load()
    assert cfg.base_dir == tmp_path
    assert cfg.chunk_duration == 120
    assert cfg.mode == "live"
    assert cfg.model == "haas-ja-v1.0:q4_k"
    assert cfg.capture_mic is False
    assert cfg.retention_days == 7


def test_config_toml_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBA_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        'mode = "record-only"\n'
        "chunk_duration = 60\n"
        "capture_mic = true\n",
        encoding="utf-8",
    )
    cfg = config.load()
    assert cfg.mode == "record-only"
    assert cfg.chunk_duration == 60
    assert cfg.capture_mic is True


def test_unknown_key_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBA_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        'nonexistent_key = "boom"\nmodel = "custom-model"\n',
        encoding="utf-8",
    )
    cfg = config.load()
    assert cfg.model == "custom-model"
    assert not hasattr(cfg, "nonexistent_key")


def test_base_dir_not_overridable(tmp_path, monkeypatch):
    """config.toml の base_dir は無視される（SCRIBA_HOME が正）。"""
    monkeypatch.setenv("SCRIBA_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text('base_dir = "/tmp/evil"\n', encoding="utf-8")
    cfg = config.load()
    assert cfg.base_dir == tmp_path


def test_dictionary_path_default(tmp_path):
    cfg = Config(base_dir=tmp_path)
    assert cfg.dictionary_path == tmp_path / "dict.yaml"
