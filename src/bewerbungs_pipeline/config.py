import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    db_path: Path
    out_dir: Path
    template_path: Path
    profile_path: Path
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    web_token: str = ""
    # Extra host names accepted in loopback mode, e.g. the Tailscale name behind Pforte.
    allowed_hosts: frozenset[str] = frozenset()


def load_config() -> Config:
    return Config(
        db_path=Path(os.getenv("DB_PATH", "data/jobs.db")),
        out_dir=Path(os.getenv("OUT_DIR", "out")),
        template_path=Path(os.getenv("TEMPLATE_PATH", "templates/beispiel.html")),
        profile_path=Path(os.getenv("PROFILE_PATH", "profile.yaml")),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        web_token=os.getenv("JOBS_WEB_TOKEN", ""),
        allowed_hosts=frozenset(
            h.strip() for h in os.getenv("JOBS_ALLOWED_HOSTS", "").split(",") if h.strip()
        ),
    )
