import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///job_scraper.db")

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS scrape_targets (
        source_type TEXT NOT NULL,
        target_value TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (source_type, target_value)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS seen_jobs (
        job_url TEXT PRIMARY KEY,
        source_type TEXT NOT NULL,
        target_value TEXT,
        company_name TEXT,
        title TEXT,
        location TEXT,
        first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


def create_storage(database_url=None):
    return Storage(database_url or DEFAULT_DATABASE_URL)


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

    def load_seen_urls(self):
        rows = self._fetch_all(
            "SELECT job_url FROM seen_jobs",
            (),
        )
        return {row["job_url"] for row in rows}

    def store_seen_jobs(self, jobs):
        rows = [
            (
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
                    INSERT OR IGNORE INTO seen_jobs (
                        job_url,
                        source_type,
                        target_value,
                        company_name,
                        title,
                        location
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
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
                    INSERT INTO seen_jobs (
                        job_url,
                        source_type,
                        target_value,
                        company_name,
                        title,
                        location
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (job_url) DO NOTHING
                    """,
                    rows,
                )
            connection.commit()
        finally:
            connection.close()

    def seed_targets(self, target_map):
        # Insert missing targets without overwriting enable/disable choices saved in the DB.
        rows = []
        for source_type, target_values in target_map.items():
            for target_value in target_values:
                rows.append((source_type, target_value))

        if not rows:
            return

        if self.backend == "sqlite":
            connection = self._connect_sqlite()
            try:
                connection.executemany(
                    """
                    INSERT OR IGNORE INTO scrape_targets (
                        source_type,
                        target_value,
                        enabled
                    )
                    VALUES (?, ?, 1)
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
                    INSERT INTO scrape_targets (
                        source_type,
                        target_value,
                        enabled
                    )
                    VALUES (%s, %s, 1)
                    ON CONFLICT (source_type, target_value) DO NOTHING
                    """,
                    rows,
                )
            connection.commit()
        finally:
            connection.close()

    def load_targets(self, source_type):
        rows = self._fetch_all(
            self._sql(
                """
                SELECT target_value
                FROM scrape_targets
                WHERE source_type = {placeholder}
                  AND enabled = 1
                ORDER BY target_value
                """
            ),
            (source_type,),
        )
        return [row["target_value"] for row in rows]

    def list_targets(self, source_type=None):
        if source_type:
            rows = self._fetch_all(
                self._sql(
                    """
                    SELECT source_type, target_value, enabled
                    FROM scrape_targets
                    WHERE source_type = {placeholder}
                    ORDER BY source_type, target_value
                    """
                ),
                (source_type,),
            )
            return rows

        return self._fetch_all(
            """
            SELECT source_type, target_value, enabled
            FROM scrape_targets
            ORDER BY source_type, target_value
            """,
            (),
        )

    def upsert_target(self, source_type, target_value, enabled=1):
        row = (source_type, target_value, enabled)

        if self.backend == "sqlite":
            connection = self._connect_sqlite()
            try:
                connection.execute(
                    """
                    INSERT INTO scrape_targets (
                        source_type,
                        target_value,
                        enabled
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(source_type, target_value)
                    DO UPDATE SET enabled = excluded.enabled
                    """,
                    row,
                )
                connection.commit()
            finally:
                connection.close()
            return

        connection = self._connect_postgres()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO scrape_targets (
                        source_type,
                        target_value,
                        enabled
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (source_type, target_value)
                    DO UPDATE SET enabled = EXCLUDED.enabled
                    """,
                    row,
                )
            connection.commit()
        finally:
            connection.close()

    def set_target_enabled(self, source_type, target_value, enabled):
        if self.backend == "sqlite":
            connection = self._connect_sqlite()
            try:
                connection.execute(
                    """
                    UPDATE scrape_targets
                    SET enabled = ?
                    WHERE source_type = ?
                      AND target_value = ?
                    """,
                    (enabled, source_type, target_value),
                )
                connection.commit()
            finally:
                connection.close()
            return

        connection = self._connect_postgres()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE scrape_targets
                    SET enabled = %s
                    WHERE source_type = %s
                      AND target_value = %s
                    """,
                    (enabled, source_type, target_value),
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

        return psycopg.connect(self.database_url)

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
