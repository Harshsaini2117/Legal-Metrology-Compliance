"""SQLite persistence for completed scan records."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class ScanRepository:
    """Persist and retrieve completed scan metadata without external services."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def create_scan(
        self,
        scan_result: dict[str, Any],
        original_filename: str | None,
        scan_id: str | None = None,
    ) -> dict[str, Any]:
        """Store a completed scan and return its persisted history record."""
        compliance_report = _mapping(scan_result.get("compliance_report"))
        record = {
            "scan_id": scan_id or uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "original_filename": original_filename or Path(str(scan_result.get("input_image", ""))).name,
            "processing_status": scan_result.get("processing_status", "COMPLETED"),
            "extracted_fields": _mapping(scan_result.get("extracted_fields")),
            "compliance_report_summary": {
                "overall_status": compliance_report.get("overall_status"),
                "compliance_score": compliance_report.get("compliance_score"),
            },
            "violations": _list(compliance_report.get("violations")),
            "report_path": scan_result.get("report_path"),
            "report_filename": scan_result.get("report_filename"),
        }

        with self._connection() as connection:
            self._initialize(connection)
            connection.execute(
                """
                INSERT INTO scans (
                    scan_id, timestamp, original_filename, processing_status,
                    extracted_fields, compliance_report_summary, violations,
                    report_path, report_filename
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["scan_id"],
                    record["timestamp"],
                    record["original_filename"],
                    record["processing_status"],
                    json.dumps(record["extracted_fields"]),
                    json.dumps(record["compliance_report_summary"]),
                    json.dumps(record["violations"]),
                    record["report_path"],
                    record["report_filename"],
                ),
            )
        return record

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return newest persisted scans first."""
        with self._connection() as connection:
            self._initialize(connection)
            rows = connection.execute(
                "SELECT * FROM scans ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_scan(self, scan_id: str) -> dict[str, Any] | None:
        """Return a persisted scan by identifier, if it exists."""
        with self._connection() as connection:
            self._initialize(connection)
            row = connection.execute(
                "SELECT * FROM scans WHERE scan_id = ?", (scan_id,)
            ).fetchone()
        return _row_to_record(row) if row else None

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                scan_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                processing_status TEXT NOT NULL,
                extracted_fields TEXT NOT NULL,
                compliance_report_summary TEXT NOT NULL,
                violations TEXT NOT NULL,
                report_path TEXT,
                report_filename TEXT
            )
            """
        )


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "scan_id": row["scan_id"],
        "timestamp": row["timestamp"],
        "original_filename": row["original_filename"],
        "processing_status": row["processing_status"],
        "extracted_fields": json.loads(row["extracted_fields"]),
        "compliance_report_summary": json.loads(row["compliance_report_summary"]),
        "violations": json.loads(row["violations"]),
        "report_path": row["report_path"],
        "report_filename": row["report_filename"],
    }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []
