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
# No SMTP host, so the mailer uses its file transport and the tests can read
# back what was actually sent.
os.environ.setdefault("MAIL_OUTBOX_DIR", str(_TMP / "mail"))
os.environ.setdefault("RUNTIME_PROFILE", "local")
os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("EMBEDDING_ENABLED", "false")
os.environ.setdefault("ANTIMALWARE_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def app_database():
    """Create the application schema in the shared test database."""
    from cabqp.shared import models  # noqa: F401 - registers every table on Base
    from cabqp.shared.db import Base, engine

    Base.metadata.create_all(engine)
    yield engine
