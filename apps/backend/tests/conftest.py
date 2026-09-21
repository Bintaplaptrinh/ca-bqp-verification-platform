import os
import tempfile
from pathlib import Path

# A file-backed SQLite database rather than ":memory:": the API now reads
# accounts and sessions through the process-wide SessionLocal, and an in-memory
# SQLite database is not shared across the connections/threads a TestClient
# request goes through. Most tests still build their own isolated engine and
# never touch this one.
_TMP = Path(tempfile.mkdtemp(prefix="cabqp-tests-"))
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_TMP / 'app.db'}")
os.environ.setdefault("STORAGE_ROOT", str(_TMP / "documents"))
# Gmail SMTP is the only mail transport; `mail_stub` replaces the socket below,
# so these only have to satisfy Settings.mail_configured.
os.environ.setdefault("GMAIL_USER", "cabqp-test@gmail.com")
os.environ.setdefault("GMAIL_APP_PASSWORD", "test-app-password")
os.environ.setdefault("RUNTIME_PROFILE", "local")
os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("EMBEDDING_ENABLED", "false")
os.environ.setdefault("ANTIMALWARE_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def app_database():
    """Create the application schema in the shared test database."""
    from cabqp.shared import models  # noqa: F401 - registers every table on Base
    from cabqp.shared.db import Base, engine

    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture(autouse=True)
def stub_gmail_smtp(monkeypatch):
    """Never open a socket to Gmail; record what would have been sent."""
    import mail_stub

    return mail_stub.install(monkeypatch)
