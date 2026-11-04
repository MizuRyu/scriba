"""設定ファイル（{base_dir}/config.toml）の読み込み。"""

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_BASE_DIR = "~/scriba"


@dataclass
class Config:
    base_dir: Path
    # F1: 録音
    device_system: str = "BlackHole 2ch"
    device_mic: str = "外部マイク"
    chunk_duration: int = 120
    sample_rate: int = 16000
    multi_output_device: str = "複数出力装置"
    # F2: 文字起こし
    mode: str = "live"  # live | record-only
    model: str = "haas-ja-v1.0:q4_k"
    language: str = "ja"
    transcribe_on_stop: bool = True
    # liveでマイクも併録し[自分]/[相手]を分離する。falseならsystem単一トラック
    # （自分の声は記録されない）
    capture_mic: bool = False
    # F3: 保存先
    session_format: str = "%Y%m%d-%H%M%S"
    # F4: クリーンアップ
    retention_days: int = 7
    cleanup_target: str = "chunks"  # chunks | all
    # F1: タイムアウト
    max_recording_min: int = 180  # 3時間で強制停止
    auto_stop: bool = True  # systemのチャンクが丸ごと無音で、同じチャンクのmicにも発話がなければ自動停止
    # 待機画面だけや、誤って入った会議の録音を残さない。これより短い録音は停止時に破棄（0で無効）
    min_keep_sec: int = 60
    # F6: ビューアサーバーの自動停止（0で無効）
    serve_timeout_min: int = 180
    # F7: 辞書
    dict_path: str = ""  # 空なら {base_dir}/dict.yaml
    filters_enabled: bool = True  # false ならフィルタ除去しない
    # F8: カレンダー照合・enrich
    calendar_source: str = ""  # json | ics。空で calendar_path があれば json
    calendar_path: str = ""  # json: ファイル / ics: ファイルまたは http(s) URL
    # F9: export
    export_dir: str = ""  # 空なら export しない
    export_subdir: str = "transcript/{project}"
    # F1: 自動録音（watch）で会議中とみなすアプリ（bundle id の接頭辞）
    meeting_apps: list = field(default_factory=lambda: ["com.microsoft.teams"])
    enrich_organizations: dict = None  # type: ignore[assignment]
    enrich_projects: list = None  # type: ignore[assignment]

    @property
    def sessions_dir(self) -> Path:
        return self.base_dir / "sessions"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    @property
    def perf_log(self) -> Path:
        return self.logs_dir / "performance.jsonl"

    @property
    def state_file(self) -> Path:
        return self.base_dir / "state.json"

    @property
    def dictionary_path(self) -> Path:
        return Path(self.dict_path).expanduser() if self.dict_path else self.base_dir / "dict.yaml"

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id


def load() -> Config:
    base_dir = Path(os.environ.get("SCRIBA_HOME", DEFAULT_BASE_DIR)).expanduser()
    cfg_file = base_dir / "config.toml"
    values: dict = {}
    enrich_orgs = {}
    enrich_projects = []
    if cfg_file.exists():
        with open(cfg_file, "rb") as f:
            raw = tomllib.load(f)
        known = {f.name for f in fields(Config)}
        enrich = raw.pop("enrich", {})
        enrich_orgs = enrich.get("organizations", {})
        enrich_projects = enrich.get("projects", [])
        values = {k: v for k, v in raw.items() if k in known and k != "base_dir"}
    cfg = Config(base_dir=base_dir, **values)
    if cfg.enrich_organizations is None:
        cfg.enrich_organizations = enrich_orgs
    if cfg.enrich_projects is None:
        cfg.enrich_projects = enrich_projects
    return cfg
