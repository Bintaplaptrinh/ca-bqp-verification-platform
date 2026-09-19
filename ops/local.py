#!/usr/bin/env python
"""Run the whole platform locally, without Docker.

    conda run -n bqp python ops/local.py start

Brings up a dedicated PostgreSQL cluster, applies migrations, seeds the registry
and the two delivered accounts, then starts the API and the web dev server. In
this profile the API process is also the task runner and documents are stored on
disk, so PostgreSQL is the only service involved — no Redis, MinIO or Keycloak.

The cluster runs on port 5433 with its data directory under ``~/.local/share``:
the system cluster on 5432 does not grant this user database-creation rights,
and the project volume does not enforce the directory permissions PostgreSQL
requires.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local"
PGDATA = Path.home() / ".local/share/cabqp/postgres"
PGPORT = 5433
DB_NAME = "cabqp_verification"
DB_ROLE = "cabqp_app"
BACKEND_SRC = ROOT / "apps/backend/src"

PGBIN = Path(subprocess.check_output(["/usr/bin/pg_config", "--bindir"], text=True).strip())

SERVICES = {
    "backend": "http://127.0.0.1:8000/health/live",
    "web": "http://127.0.0.1:3000/",
}

STATE.mkdir(exist_ok=True)


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def ready(url: str) -> bool:
    try:
        with urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def _unquote(value: str) -> str:
    """Drop one layer of matching surrounding quotes, as dotenv readers do.

    These values become real environment variables, which take priority over
    pydantic's own ``.env`` lookup — and pydantic never strips quotes from a
    real environment variable. Leaving them on turned
    ``GMAIL_APP_PASSWORD="abcd efgh ijkl mnop"`` into a literal 21-character
    string that Gmail rejected with ``SMTPAuthenticationError``, and
    ``MAIL_FROM_NAME`` into a display name wearing its own quotes.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_env_file() -> dict[str, str]:
    """Parse the repo-root ``.env`` into a plain mapping."""
    values: dict[str, str] = {}
    env_file = ROOT / ".env"
    if not env_file.exists():
        return values
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, _, value = line.partition("=")
        values[key.strip()] = _unquote(value.strip())
    return values


def app_env() -> dict:
    """Environment every child process inherits.

    The root ``.env`` is injected explicitly rather than left to pydantic's own
    lookup: alembic and the seed scripts run with ``apps/backend`` as their
    working directory, where a relative ``.env`` does not resolve.

    ``PATH`` is prefixed with the active interpreter's directory so the
    binaries installed alongside it (poppler) are found without a separate
    system install.
    """
    return {
        **os.environ,
        **read_env_file(),
        "PYTHONPATH": str(BACKEND_SRC),
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
        # transformers refuses to import against the stale TensorFlow install in
        # this environment unless the Torch backend is selected explicitly.
        "USE_TF": "0",
        "USE_TORCH": "1",
    }


# --- Database ----------------------------------------------------------------


def _cluster_running() -> bool:
    return (
        subprocess.run(
            [str(PGBIN / "pg_ctl"), "-D", str(PGDATA), "status"], stdout=subprocess.DEVNULL
        ).returncode
        == 0
    )


def start_cluster() -> None:
    if not (PGDATA / "PG_VERSION").exists():
        PGDATA.mkdir(parents=True, exist_ok=True)
        run(
            [
                PGBIN / "initdb",
                "-D",
                PGDATA,
                "--auth-local=peer",
                "--auth-host=scram-sha-256",
                "--encoding=UTF8",
                "--no-locale",
            ]
        )
    if not _cluster_running():
        run(
            [
                PGBIN / "pg_ctl",
                "-D",
                PGDATA,
                "-l",
                PGDATA.parent / "postgres.log",
                "-o",
                f"-p {PGPORT} -h 127.0.0.1 -k /tmp",
                "start",
            ]
        )
        for _ in range(50):
            if _cluster_running():
                break
            time.sleep(0.2)


def ensure_database() -> str:
    """Create the role/database if absent and return the DATABASE_URL."""
    import psycopg2
    from psycopg2 import sql

    env_file = ROOT / ".env"
    url = read_env_file().get("DATABASE_URL")
    if url and _database_reachable(url):
        return url

    password = secrets.token_urlsafe(32)
    admin = psycopg2.connect(dbname="postgres", host="/tmp", port=PGPORT)
    admin.autocommit = True
    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (DB_ROLE,))
            if cursor.fetchone():
                cursor.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD %s").format(sql.Identifier(DB_ROLE)),
                    (password,),
                )
            else:
                cursor.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(DB_ROLE)),
                    (password,),
                )
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if not cursor.fetchone():
                cursor.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(DB_NAME), sql.Identifier(DB_ROLE)
                    )
                )
    finally:
        admin.close()

    # psycopg (v3) is what the backend's SQLAlchemy URL uses.
    url = f"postgresql+psycopg://{DB_ROLE}:{password}@127.0.0.1:{PGPORT}/{DB_NAME}"
    lines = [
        f"DATABASE_URL={url}",
        "RUNTIME_PROFILE=local",
        "AUTH_DISABLED=false",
        "APP_ENV=development",
        "ANTIMALWARE_ENABLED=false",
        "RATE_LIMIT_ENABLED=false",
        "EMBEDDING_ENABLED=true",
        "STORAGE_ROOT=.local/documents",
        "CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000",
        f"POPPLER_PATH={Path(sys.executable).parent}",
    ]
    # Anything already in the file that this profile does not generate — the
    # GMAIL_USER / GMAIL_APP_PASSWORD credential above all — is carried over, so
    # regenerating the database password does not silently disable outgoing mail.
    generated = {line.split("=", 1)[0] for line in lines}
    kept = [f"{k}={v}" for k, v in read_env_file().items() if k not in generated]
    env_file.write_text("\n".join(lines + kept) + "\n", encoding="utf-8")
    print(f"Wrote {env_file} with a freshly generated database password.")
    return url


def _database_reachable(url: str) -> bool:
    try:
        import sqlalchemy

        engine = sqlalchemy.create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(sqlalchemy.text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


def migrate() -> None:
    run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "apps/backend",
        env=app_env(),
    )


def seed() -> None:
    env = app_env()
    run([sys.executable, "scripts/seed.py"], cwd=ROOT / "apps/backend", env=env)
    run([sys.executable, "scripts/seed_accounts.py"], cwd=ROOT / "apps/backend", env=env)


def init() -> None:
    start_cluster()
    ensure_database()
    migrate()
    seed()


# --- Processes ---------------------------------------------------------------


def _service_commands() -> list[tuple[str, str, list]]:
    return [
        (
            "backend",
            SERVICES["backend"],
            [
                sys.executable,
                "-m",
                "uvicorn",
                "cabqp.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--app-dir",
                str(BACKEND_SRC),
            ],
        ),
        (
            "web",
            SERVICES["web"],
            ["npm", "run", "dev", "--prefix", "apps/web", "--", "--host", "127.0.0.1", "--port", "3000"],
        ),
    ]


def start() -> None:
    init()
    env = app_env()
    for name, url, command in _service_commands():
        if ready(url):
            print(f"{name}: already running at {url}")
            continue
        with (STATE / f"{name}.log").open("a") as log:
            process = subprocess.Popen(
                [str(x) for x in command],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        (STATE / f"{name}.pid").write_text(str(process.pid))
        # The backend loads OCR and embedding models on first import, which is
        # slow on a cold cache; give it a generous window before declaring it dead.
        deadline = time.monotonic() + (180 if name == "backend" else 90)
        while time.monotonic() < deadline:
            if ready(url):
                break
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited during startup; see .local/{name}.log")
            time.sleep(0.5)
        else:
            raise RuntimeError(f"{name} did not become ready; see .local/{name}.log")
        print(f"{name}: {url}")

    print()
    print("  Giao diện:  http://127.0.0.1:3000")
    print("  API/OpenAPI: http://127.0.0.1:8000/docs")
    print("  Đăng nhập:  admin/admin (quản trị)  ·  user/user (tra cứu)")


def stop() -> None:
    for name in ["web", "backend"]:
        path = STATE / f"{name}.pid"
        if not path.exists():
            continue
        pid = int(path.read_text())
        # Only signal a process that still looks like the one this script started;
        # the pid may have been recycled since.
        cmdline = Path(f"/proc/{pid}/cmdline")
        command = cmdline.read_bytes() if cmdline.exists() else b""
        expected = b"cabqp.main:app" if name == "backend" else b"npm"
        if expected in command:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        path.unlink()
    print("Application processes stopped. PostgreSQL remains running.")


def status() -> None:
    print(f"postgres (port {PGPORT}): {'running' if _cluster_running() else 'stopped'}")
    for name, url in SERVICES.items():
        print(f"{name}: {'ready' if ready(url) else 'not responding'} ({url})")
    if ready("http://127.0.0.1:8000/health/ready"):
        with urlopen("http://127.0.0.1:8000/health/ready", timeout=3) as response:
            print("readiness:", json.dumps(json.load(response)["checks"], ensure_ascii=False))


# --- Backup ------------------------------------------------------------------


def _database_url() -> str:
    start_cluster()
    return ensure_database()


def backup(drill: bool = False) -> None:
    import sqlalchemy

    url = sqlalchemy.make_url(_database_url())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = STATE / "backups" / stamp
    destination.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "PGPASSWORD": url.password or ""}
    options = ["-h", url.host, "-p", str(url.port or PGPORT), "-U", url.username]
    run([PGBIN / "pg_dump", *options, "-Fc", "-f", destination / "database.dump", url.database], env=env)

    with tarfile.open(destination / "documents.tar.gz", "w:gz") as archive:
        documents = STATE / "documents"
        if documents.exists():
            archive.add(documents, arcname="documents")

    if drill:
        _restore_drill(url, options, env, destination)

    print(f"Backup: {destination}")


def _restore_drill(url, options, env, destination: Path) -> None:
    """Restore into a throwaway database and compare row counts.

    No live database is touched: the temporary one is dropped either way.
    """
    import psycopg2
    import sqlalchemy
    from psycopg2 import sql

    target = "cabqp_restore_" + secrets.token_hex(4)
    admin = psycopg2.connect(dbname="postgres", host="/tmp", port=PGPORT)
    admin.autocommit = True
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(target), sql.Identifier(DB_ROLE)
                )
            )
        run(
            [
                PGBIN / "pg_restore",
                *options,
                "--no-owner",
                "--exit-on-error",
                "-d",
                target,
                destination / "database.dump",
            ],
            env=env,
        )
        restored_engine = sqlalchemy.create_engine(str(url.set(database=target)))
        source_engine = sqlalchemy.create_engine(str(url))
        try:
            with restored_engine.connect() as connection:
                restored_count = connection.scalar(sqlalchemy.text("SELECT count(*) FROM cases"))
            with source_engine.connect() as connection:
                source_count = connection.scalar(sqlalchemy.text("SELECT count(*) FROM cases"))
        finally:
            restored_engine.dispose()
            source_engine.dispose()

        if restored_count != source_count:
            raise RuntimeError(
                f"Restore drill failed: {restored_count} cases restored, {source_count} expected"
            )
        (destination / "restore-check.json").write_text(
            json.dumps({"source_cases": source_count, "restored_cases": restored_count, "status": "passed"})
        )
        print(f"Restore drill passed: {restored_count} cases")
    finally:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(target)))
        admin.close()


COMMANDS = {
    "init": init,
    "start": start,
    "stop": stop,
    "status": status,
    "migrate": lambda: (start_cluster(), ensure_database(), migrate()),
    "seed": lambda: (start_cluster(), ensure_database(), seed()),
    "backup": backup,
    "restore-drill": lambda: backup(drill=True),
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(COMMANDS))
    COMMANDS[parser.parse_args().command]()
