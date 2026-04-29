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

REVIEW_AUDIT_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS recipient_review_audit (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        recipient_id TEXT NOT NULL,
        job_url TEXT NOT NULL,
        source_type TEXT,
        target_value TEXT,
        company_name TEXT,
        title TEXT,
        location TEXT,
        review_family TEXT NOT NULL,
        classification TEXT NOT NULL,
        stage TEXT,
        seen_recorded INTEGER NOT NULL DEFAULT 0,
        sent INTEGER NOT NULL DEFAULT 0,
        hard_filter_reason TEXT,
        semantic_rank INTEGER,
        raw_embedding_score REAL,
        semantic_score REAL,
        semantic_threshold REAL,
        semantic_top_profile TEXT,
        semantic_second_profile TEXT,
        semantic_fit_summary TEXT,
        title_boost_multiplier REAL,
        salary_upper_bound_gbp REAL,
        salary_penalty_applied REAL,
        gemini_pass1_score INTEGER,
        gemini_pass2_score INTEGER,
        gemini_matched_profile TEXT,
        gemini_reason TEXT,
        supporting_evidence_json TEXT,
        mismatch_evidence_json TEXT,
        review_error_stage TEXT,
        review_error TEXT,
        metadata_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_recipient_review_audit_recipient_created
    ON recipient_review_audit (recipient_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_recipient_review_audit_run
    ON recipient_review_audit (run_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_recipient_review_audit_classification
    ON recipient_review_audit (classification)
    """,
]

POSTGRES_REVIEW_AUDIT_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS recipient_review_audit (
        audit_id BIGSERIAL PRIMARY KEY,
        run_id TEXT NOT NULL,
        recipient_id TEXT NOT NULL,
        job_url TEXT NOT NULL,
        source_type TEXT,
        target_value TEXT,
        company_name TEXT,
        title TEXT,
        location TEXT,
        review_family TEXT NOT NULL,
        classification TEXT NOT NULL,
        stage TEXT,
        seen_recorded BOOLEAN NOT NULL DEFAULT FALSE,
        sent BOOLEAN NOT NULL DEFAULT FALSE,
        hard_filter_reason TEXT,
        semantic_rank INTEGER,
        raw_embedding_score DOUBLE PRECISION,
        semantic_score DOUBLE PRECISION,
        semantic_threshold DOUBLE PRECISION,
        semantic_top_profile TEXT,
        semantic_second_profile TEXT,
        semantic_fit_summary TEXT,
        title_boost_multiplier DOUBLE PRECISION,
        salary_upper_bound_gbp DOUBLE PRECISION,
        salary_penalty_applied DOUBLE PRECISION,
        gemini_pass1_score INTEGER,
        gemini_pass2_score INTEGER,
        gemini_matched_profile TEXT,
        gemini_reason TEXT,
        supporting_evidence_json JSONB,
        mismatch_evidence_json JSONB,
        review_error_stage TEXT,
        review_error TEXT,
        metadata_json JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_recipient_review_audit_recipient_created
    ON recipient_review_audit (recipient_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_recipient_review_audit_run
    ON recipient_review_audit (run_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_recipient_review_audit_classification
    ON recipient_review_audit (classification)
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

DEFAULT_AUDIT_KEEP_ROWS = 1000
DEFAULT_AUDIT_HIGH_WATER_ROWS = 1500

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

    def load_recipient_profile_configs(self, enabled_only=True):
        rows = self.load_recipient_profile_records(enabled_only=enabled_only)
        configs = []
        for row in rows:
            parsed = row.get("config")
            if isinstance(parsed, dict):
                configs.append(parsed)
        return configs

    def load_recipient_profile_records(self, enabled_only=True):
        rows = self._fetch_all(
            f"""
            SELECT recipient_id, email, enabled, config_json, created_at, updated_at
            FROM {self._recipient_profiles_table_name()}
            {"WHERE enabled = " + self._true_literal() if enabled_only else ""}
            ORDER BY recipient_id
            """,
            (),
        )
        records = []
        for row in rows:
            parsed = self._load_json_field(row.get("config_json"))
            if not isinstance(parsed, dict):
                continue
            records.append(
                {
                    **row,
                    "enabled": self._coerce_bool(row.get("enabled")),
                    "config": parsed,
                }
            )
        return records

    def load_recipient_profile_versions(self, recipient_id, limit=20):
        rows = self._fetch_all(
            self._sql(
                f"""
                SELECT version_id, recipient_id, email, enabled, config_json, saved_at
                FROM {self._recipient_profile_versions_table_name()}
                WHERE recipient_id = {{placeholder}}
                ORDER BY saved_at DESC, version_id DESC
                LIMIT {{placeholder}}
                """
            ),
            (recipient_id, max(1, int(limit))),
        )
        versions = []
        for row in rows:
            parsed = self._load_json_field(row.get("config_json"))
            if not isinstance(parsed, dict):
                continue
            versions.append(
                {
                    **row,
                    "enabled": self._coerce_bool(row.get("enabled")),
                    "config": parsed,
                }
            )
        return versions

    def load_recipient_profile_version(self, recipient_id, version_id):
        rows = self._fetch_all(
            self._sql(
                f"""
                SELECT version_id, recipient_id, email, enabled, config_json, saved_at
                FROM {self._recipient_profile_versions_table_name()}
                WHERE recipient_id = {{placeholder}}
                  AND version_id = {{placeholder}}
                """
            ),
            (recipient_id, version_id),
        )
        if not rows:
            return None

        row = rows[0]
        parsed = self._load_json_field(row.get("config_json"))
        if not isinstance(parsed, dict):
            return None
        return {
            **row,
            "enabled": self._coerce_bool(row.get("enabled")),
            "config": parsed,
        }

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

    def store_review_audit_rows(self, recipient_id, run_id, audit_rows):
        rows = [
            self._normalize_review_audit_row(recipient_id, run_id, row)
            for row in audit_rows
            if row.get("job_url")
        ]
        if not rows:
            return

        columns = [
            "run_id",
            "recipient_id",
            "job_url",
            "source_type",
            "target_value",
            "company_name",
            "title",
            "location",
            "review_family",
            "classification",
            "stage",
            "seen_recorded",
            "sent",
            "hard_filter_reason",
            "semantic_rank",
            "raw_embedding_score",
            "semantic_score",
            "semantic_threshold",
            "semantic_top_profile",
            "semantic_second_profile",
            "semantic_fit_summary",
            "title_boost_multiplier",
            "salary_upper_bound_gbp",
            "salary_penalty_applied",
            "gemini_pass1_score",
            "gemini_pass2_score",
            "gemini_matched_profile",
            "gemini_reason",
            "supporting_evidence_json",
            "mismatch_evidence_json",
            "review_error_stage",
            "review_error",
            "metadata_json",
        ]

        if self.backend == "sqlite":
            placeholders = ", ".join("?" for _column in columns)
            connection = self._connect_sqlite()
            try:
                connection.executemany(
                    f"""
                    INSERT INTO recipient_review_audit (
                        {", ".join(columns)}
                    )
                    VALUES ({placeholders})
                    """,
                    [tuple(row[column] for column in columns) for row in rows],
                )
                connection.commit()
            finally:
                connection.close()
            self.prune_review_audit_rows()
            return

        connection = self._connect_postgres()
        try:
            with connection.cursor() as cursor:
                value_placeholders = [
                    "%s::jsonb"
                    if column
                    in {
                        "supporting_evidence_json",
                        "mismatch_evidence_json",
                        "metadata_json",
                    }
                    else "%s"
                    for column in columns
                ]
                for row in rows:
                    cursor.execute(
                        f"""
                        INSERT INTO recipient_review_audit (
                            {", ".join(columns)}
                        )
                        VALUES (
                            {", ".join(value_placeholders)}
                        )
                        """,
                        tuple(row[column] for column in columns),
                    )
            connection.commit()
        finally:
            connection.close()
        self.prune_review_audit_rows()

    def prune_review_audit_rows(self, keep_rows=None, high_water_rows=None):
        keep_rows, high_water_rows = self._review_audit_retention_limits(
            keep_rows,
            high_water_rows,
        )
        row_count = self._review_audit_row_count()
        if row_count <= high_water_rows:
            return 0

        delete_count = row_count - keep_rows
        if delete_count <= 0:
            return 0

        if self.backend == "sqlite":
            connection = self._connect_sqlite()
            try:
                cursor = connection.execute(
                    """
                    DELETE FROM recipient_review_audit
                    WHERE audit_id IN (
                        SELECT audit_id
                        FROM recipient_review_audit
                        ORDER BY created_at ASC, audit_id ASC
                        LIMIT ?
                    )
                    """,
                    (delete_count,),
                )
                connection.commit()
                return cursor.rowcount
            finally:
                connection.close()

        connection = self._connect_postgres()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM recipient_review_audit
                    WHERE audit_id IN (
                        SELECT audit_id
                        FROM recipient_review_audit
                        ORDER BY created_at ASC, audit_id ASC
                        LIMIT %s
                    )
                    """,
                    (delete_count,),
                )
                deleted_rows = cursor.rowcount
            connection.commit()
            return deleted_rows
        finally:
            connection.close()

    def load_review_audit_rows(
        self,
        limit=None,
        recipient_id=None,
        classification=None,
        review_family=None,
        run_id=None,
        latest_first=False,
        sort=None,
    ):
        filters = []
        params = []
        placeholder = "?" if self.backend == "sqlite" else "%s"

        for column_name, value in (
            ("recipient_id", recipient_id),
            ("classification", classification),
            ("review_family", review_family),
            ("run_id", run_id),
        ):
            if value:
                filters.append(f"{column_name} = {placeholder}")
                params.append(value)

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        order_clause = self._review_audit_order_clause(sort, latest_first)
        limit_clause = ""
        if limit is not None:
            limit_clause = f"LIMIT {placeholder}"
            params.append(max(1, int(limit)))

        return self._fetch_all(
            f"""
            SELECT *
            FROM recipient_review_audit
            {where_clause}
            ORDER BY {order_clause}
            {limit_clause}
            """,
            tuple(params),
        )

    def load_review_audit_filter_values(self):
        rows = self._fetch_all(
            """
            SELECT recipient_id, review_family, classification, run_id
            FROM recipient_review_audit
            ORDER BY created_at DESC, audit_id DESC
            """,
            (),
        )
        return {
            "recipient_ids": self._unique_values(row.get("recipient_id") for row in rows),
            "review_families": self._unique_values(row.get("review_family") for row in rows),
            "classifications": self._unique_values(row.get("classification") for row in rows),
            "run_ids": self._unique_values(row.get("run_id") for row in rows),
        }

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
            for statement in REVIEW_AUDIT_SCHEMA_STATEMENTS:
                connection.execute(statement)
            self._ensure_sqlite_columns(
                connection,
                "recipient_review_audit",
                {"raw_embedding_score": "REAL"},
            )
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
                for statement in POSTGRES_REVIEW_AUDIT_SCHEMA_STATEMENTS:
                    cursor.execute(statement)
                cursor.execute(
                    """
                    ALTER TABLE recipient_review_audit
                    ADD COLUMN IF NOT EXISTS raw_embedding_score DOUBLE PRECISION
                    """
                )
                for statement in POSTGRES_RECIPIENT_PROFILE_SCHEMA_STATEMENTS:
                    cursor.execute(statement)
            connection.commit()
        finally:
            connection.close()

    def _connect_sqlite(self):
        connection = sqlite3.connect(self.sqlite_path)
        return connection

    @staticmethod
    def _ensure_sqlite_columns(connection, table_name, columns):
        existing_columns = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table_name})")
        }
        for column_name, column_type in columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )

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

    def _recipient_profile_versions_table_name(self):
        if self.backend == "sqlite":
            return "recipient_profile_versions"
        return "app_config.recipient_profile_versions"

    def _true_literal(self):
        return "1" if self.backend == "sqlite" else "TRUE"

    @staticmethod
    def _coerce_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.lower() in {"1", "true", "t", "yes"}
        return bool(value)

    @staticmethod
    def _unique_values(values):
        return [
            value
            for value in dict.fromkeys(values)
            if value not in (None, "")
        ]

    @staticmethod
    def _review_audit_order_clause(sort, latest_first=False):
        orderings = {
            "raw_embedding_score_desc": (
                "raw_embedding_score IS NULL ASC, raw_embedding_score DESC, "
                "semantic_rank IS NULL ASC, semantic_rank ASC, audit_id ASC"
            ),
            "raw_embedding_score_asc": (
                "raw_embedding_score IS NULL ASC, raw_embedding_score ASC, "
                "semantic_rank IS NULL ASC, semantic_rank DESC, audit_id ASC"
            ),
            "semantic_score_desc": (
                "semantic_score IS NULL ASC, semantic_score DESC, "
                "semantic_rank IS NULL ASC, semantic_rank ASC, audit_id ASC"
            ),
            "semantic_score_asc": (
                "semantic_score IS NULL ASC, semantic_score ASC, "
                "semantic_rank IS NULL ASC, semantic_rank DESC, audit_id ASC"
            ),
            "semantic_rank": (
                "semantic_rank IS NULL ASC, semantic_rank ASC, audit_id ASC"
            ),
            "oldest": "created_at ASC, audit_id ASC",
            "latest": "created_at DESC, audit_id DESC",
        }
        if sort in orderings:
            return orderings[sort]

        if latest_first:
            return orderings["latest"]
        return orderings["oldest"]

    def _review_audit_row_count(self):
        rows = self._fetch_all(
            "SELECT COUNT(*) AS row_count FROM recipient_review_audit",
            (),
        )
        return int(rows[0]["row_count"]) if rows else 0

    def _review_audit_retention_limits(self, keep_rows=None, high_water_rows=None):
        keep = self._safe_int_env(
            "JOB_SCRAPER_AUDIT_KEEP_ROWS",
            DEFAULT_AUDIT_KEEP_ROWS,
            override=keep_rows,
        )
        high_water = self._safe_int_env(
            "JOB_SCRAPER_AUDIT_HIGH_WATER_ROWS",
            DEFAULT_AUDIT_HIGH_WATER_ROWS,
            override=high_water_rows,
        )
        keep = max(1, keep)
        high_water = max(keep, high_water)
        return keep, high_water

    def _normalize_review_audit_row(self, recipient_id, run_id, row):
        metadata = row.get("metadata") or {}
        return {
            "run_id": run_id,
            "recipient_id": recipient_id,
            "job_url": row.get("job_url", ""),
            "source_type": row.get("source_type", ""),
            "target_value": row.get("target_value", ""),
            "company_name": row.get("company_name", ""),
            "title": row.get("title", ""),
            "location": row.get("location", ""),
            "review_family": row.get("review_family", ""),
            "classification": row.get("classification", ""),
            "stage": row.get("stage", ""),
            "seen_recorded": bool(row.get("seen_recorded", False)),
            "sent": bool(row.get("sent", False)),
            "hard_filter_reason": row.get("hard_filter_reason"),
            "semantic_rank": row.get("semantic_rank"),
            "raw_embedding_score": row.get("raw_embedding_score"),
            "semantic_score": row.get("semantic_score"),
            "semantic_threshold": row.get("semantic_threshold"),
            "semantic_top_profile": row.get("semantic_top_profile"),
            "semantic_second_profile": row.get("semantic_second_profile"),
            "semantic_fit_summary": row.get("semantic_fit_summary"),
            "title_boost_multiplier": row.get("title_boost_multiplier"),
            "salary_upper_bound_gbp": row.get("salary_upper_bound_gbp"),
            "salary_penalty_applied": row.get("salary_penalty_applied"),
            "gemini_pass1_score": row.get("gemini_pass1_score"),
            "gemini_pass2_score": row.get("gemini_pass2_score"),
            "gemini_matched_profile": row.get("gemini_matched_profile"),
            "gemini_reason": row.get("gemini_reason"),
            "supporting_evidence_json": self._json_dump(
                row.get("supporting_evidence") or []
            ),
            "mismatch_evidence_json": self._json_dump(
                row.get("mismatch_evidence") or []
            ),
            "review_error_stage": row.get("review_error_stage"),
            "review_error": row.get("review_error"),
            "metadata_json": self._json_dump(metadata),
        }

    @staticmethod
    def _json_dump(value):
        return json.dumps(value, ensure_ascii=True)

    @staticmethod
    def _safe_int_env(name, default_value, override=None):
        if override is not None:
            return int(override)

        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            return int(default_value)

        try:
            return int(raw_value)
        except ValueError:
            return int(default_value)

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
