import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

SCHEMA_STATEMENTS = [
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


def create_storage(database_url=None):
    return Storage(database_url or os.getenv("DATABASE_URL", "sqlite:///job_scraper.db"))


class Storage:
    def __init__(self, database_url):
        self.database_url = database_url
        self.backend = self._detect_backend(database_url)
        self.sqlite_path = (
            self._resolve_sqlite_path(database_url)
            if self.backend == "sqlite"
            else None
        )

    def ensure_schema(self):
        if self.backend == "sqlite":
            self._ensure_sqlite_schema()
            return

        self._ensure_postgres_schema()

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
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()

    def _ensure_postgres_schema(self):
        connection = self._connect_postgres()
        try:
            with connection.cursor() as cursor:
                for statement in SCHEMA_STATEMENTS:
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
        return str((BASE_DIR / relative_path).resolve())
