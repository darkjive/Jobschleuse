from pathlib import Path

from bewerbungs_pipeline.config import load_config


def test_defaults(monkeypatch):
    for var in ("DB_PATH", "OUT_DIR", "TEMPLATE_PATH", "CBKS_INBOX"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.db_path == Path("data/jobs.db")
    assert cfg.template_path == Path("templates/beispiel.html")
    assert cfg.cbks_inbox is None


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("CBKS_INBOX", "/tmp/inbox")
    cfg = load_config()
    assert cfg.db_path == Path("/tmp/x.db")
    assert cfg.cbks_inbox == Path("/tmp/inbox")
