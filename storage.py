import json
import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

SEEN_JOBS_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS recipient_seen_jobs (
        recipient_id TEXT NOT NULL,
        job_url TEXT NOT NULL,
        source_type TEXT NOT NULL,
        target_value TEXT,
        company_name TEXT,
        title TEXT,
        location TEXT,
        first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (recipient_id, job_url)
    )
    """,
]

SQLITE_RECIPIENT_PROFILE_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS recipient_profiles (
        recipient_id TEXT NOT NULL PRIMARY KEY,
        email TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        config_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recipient_profile_versions (
        version_id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_id TEXT NOT NULL,
        email TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        config_json TEXT NOT NULL,
        saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

POSTGRES_RECIPIENT_PROFILE_SCHEMA_STATEMENTS = [
    "CREATE SCHEMA IF NOT EXISTS app_config",
    """
    CREATE TABLE IF NOT EXISTS app_config.recipient_profiles (
        recipient_id TEXT NOT NULL PRIMARY KEY,
        email TEXT NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        config_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_config.recipient_profile_versions (
        version_id BIGSERIAL PRIMARY KEY,
        recipient_id TEXT NOT NULL,
        email TEXT NOT NULL,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        config_json JSONB NOT NULL,
        saved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


def create_storage(database_url=None):
    return Storage(database_url or os.getenv("DATABASE_URL", "sqlite:///job_scraper.db"))


class Storage:
    def __init__(self, database_url):
        self.database_url = self._normalize_database_url(database_url)
        self.backend = self._detect_backend(self.database_url)
        self.sqlite_path = (
            self._resolve_sqlite_path(self.database_url)
            if self.backend == "sqlite"
            else None
        )

    def ensure_schema(self):
        if self.backend == "sqlite":
            self._ensure_sqlite_schema()
            return

        self._ensure_postgres_schema()

    def load_recipient_profile_configs(self, enabled_only=True):
        rows = self._fetch_all(
            f"""
            SELECT config_json
            FROM {self._recipient_profiles_table_name()}
            {"WHERE enabled = " + self._true_literal() if enabled_only else ""}
            ORDER BY recipient_id
            """,
            (),
        )
        configs = []
        for row in rows:
            parsed = self._load_json_field(row.get("config_json"))
            if isinstance(parsed, dict):
                configs.append(parsed)
        return configs

    def upsert_recipient_profile_configs(self, rows):
        if not rows:
            return

        if self.backend == "sqlite":
            connection = self._connect_sqlite()
            try:
                for row in rows:
                    serialized = json.dumps(row["config"], ensure_ascii=True)
                    connection.execute(
                        """
                        INSERT INTO recipient_profiles (
                            recipient_id,
                            email,
                            enabled,
                            config_json,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(recipient_id) DO UPDATE SET
                            email = excluded.email,
                            enabled = excluded.enabled,
                            config_json = excluded.config_json,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            row["recipient_id"],
                            row["email"],
                            1 if row["enabled"] else 0,
                            serialized,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO recipient_profile_versions (
                            recipient_id,
                            email,
                            enabled,
                            config_json
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            row["recipient_id"],
                            row["email"],
                            1 if row["enabled"] else 0,
                            serialized,
                        ),
                    )
                connection.commit()
            finally:
                connection.close()
            return

        connection = self._connect_postgres()
        try:
            with connection.cursor() as cursor:
                for row in rows:
                    serialized = json.dumps(row["config"], ensure_ascii=True)
                    cursor.execute(
                        """
                        INSERT INTO app_config.recipient_profiles (
                            recipient_id,
                            email,
                            enabled,
                            config_json,
                            updated_at
                        )
                        VALUES (%s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
                        ON CONFLICT (recipient_id) DO UPDATE SET
                            email = EXCLUDED.email,
                            enabled = EXCLUDED.enabled,
                            config_json = EXCLUDED.config_json,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            row["recipient_id"],
                            row["email"],
                            row["enabled"],
                            serialized,
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO app_config.recipient_profile_versions (
                            recipient_id,
                            email,
                            enabled,
                            config_json
                        )
                        VALUES (%s, %s, %s, %s::jsonb)
                        """,
                        (
                            row["recipient_id"],
                            row["email"],
                            row["enabled"],
                            serialized,
                        ),
                    )
            connection.commit()
        finally:
            connection.close()

    def load_seen_urls(self, recipient_id):
        rows = self._fetch_all(
            self._sql(
                """
                SELECT job_url
                FROM recipient_seen_jobs
                WHERE recipient_id = {placeholder}
                """
            ),
            (recipient_id,),
        )
        return {row["job_url"] for row in rows if row.get("job_url")}

    def store_seen_jobs(self, recipient_id, jobs):
        rows = [
            (
                recipient_id,
                job["url"],
                job["source"],
                job.get("target_value", ""),
                job.get("company", ""),
                job.get("title", ""),
                job.get("location", ""),
            )
            for job in jobs
        ]

        if not rows:
            return

        if self.backend == "sqlite":
            connection = self._connect_sqlite()
            try:
                connection.executemany(
                    """
                    INSERT OR IGNORE INTO recipient_seen_jobs (
                        recipient_id,
                        job_url,
                        source_type,
                        target_value,
                        company_name,
                        title,
                        location
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
                connection.commit()
            finally:
                connection.close()
            return

        connection = self._connect_postgres()
        try:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO recipient_seen_jobs (
                        recipient_id,
                        job_url,
                        source_type,
                        target_value,
                        company_name,
                        title,
                        location
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (recipient_id, job_url) DO NOTHING
                    """,
                    rows,
                )
            connection.commit()
        finally:
            connection.close()

    def _fetch_all(self, query, params):
        if self.backend == "sqlite":
            connection = self._connect_sqlite()
            try:
                cursor = connection.execute(query, params)
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                connection.close()

        connection = self._connect_postgres()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                columns = [column.name for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _ensure_sqlite_schema(self):
        connection = self._connect_sqlite()
        try:
            for statement in SEEN_JOBS_SCHEMA_STATEMENTS:
                connection.execute(statement)
            for statement in SQLITE_RECIPIENT_PROFILE_SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()

    def _ensure_postgres_schema(self):
        connection = self._connect_postgres()
        try:
            with connection.cursor() as cursor:
                for statement in SEEN_JOBS_SCHEMA_STATEMENTS:
                    cursor.execute(statement)
                for statement in POSTGRES_RECIPIENT_PROFILE_SCHEMA_STATEMENTS:
                    cursor.execute(statement)
            connection.commit()
        finally:
            connection.close()

    def _connect_sqlite(self):
        connection = sqlite3.connect(self.sqlite_path)
        return connection

    def _connect_postgres(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "Postgres support requires psycopg. Install dependencies from requirements.txt."
            ) from exc

        try:
            return psycopg.connect(self.database_url)
        except psycopg.OperationalError as exc:
            message = str(exc)
            if "Network is unreachable" in message:
                raise RuntimeError(
                    "Postgres connection failed because the configured host is not "
                    "reachable from GitHub Actions. If you are using Supabase, use "
                    "the pooled IPv4 connection string instead of the direct database host."
                ) from exc
            raise

    def _sql(self, template):
        placeholder = "?" if self.backend == "sqlite" else "%s"
        return template.replace("{placeholder}", placeholder)

    def _recipient_profiles_table_name(self):
        if self.backend == "sqlite":
            return "recipient_profiles"
        return "app_config.recipient_profiles"

    def _true_literal(self):
        return "1" if self.backend == "sqlite" else "TRUE"

    @staticmethod
    def _load_json_field(value):
        if isinstance(value, dict):
            return value

        if not value:
            return None

        if isinstance(value, (bytes, bytearray)):
            value = value.decode("utf-8")

        if isinstance(value, str):
            return json.loads(value)

        return None

    @staticmethod
    def _normalize_database_url(database_url):
        normalized = str(database_url or "").strip()
        if (
            len(normalized) >= 2
            and normalized[0] == normalized[-1]
            and normalized[0] in {"'", '"'}
        ):
            normalized = normalized[1:-1].strip()
        return normalized

    @staticmethod
    def _detect_backend(database_url):
        if database_url.startswith("sqlite:///"):
            return "sqlite"

        if database_url.startswith("postgres://") or database_url.startswith(
            "postgresql://"
        ):
            return "postgres"

        raise RuntimeError(
            "Unsupported DATABASE_URL. Use sqlite:///job_scraper.db or a postgres connection string."
        )

    @staticmethod
    def _resolve_sqlite_path(database_url):
        relative_path = database_url.replace("sqlite:///", "", 1)
        candidate_path = Path(relative_path)
        if candidate_path.is_absolute():
            return str(candidate_path.resolve())
        return str((BASE_DIR / candidate_path).resolve())
