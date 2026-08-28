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
    cbks_inbox: Path | None
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    web_token: str


def load_config() -> Config:
    inbox = os.getenv("CBKS_INBOX", "")
    return Config(
        db_path=Path(os.getenv("DB_PATH", "data/jobs.db")),
        out_dir=Path(os.getenv("OUT_DIR", "out")),
        template_path=Path(os.getenv("TEMPLATE_PATH", "templates/beispiel.html")),
        profile_path=Path(os.getenv("PROFILE_PATH", "profile.yaml")),
        cbks_inbox=Path(inbox) if inbox else None,
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        web_token=os.getenv("JOBS_WEB_TOKEN", ""),
    )
