"""
File upload handling for daily CSV refreshes.

Responsibilities:
    - Validate uploaded CSVs against the dataset schema (required columns)
    - Atomic write: stage to .tmp, validate, then rename to final location
    - Auto-backup the previous version before overwriting
    - Prune old backups (keep last N per dataset)

Used by the routes in src/api/main.py.
"""

import shutil
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd

from src.config import (
    DATASET_SCHEMAS,
    THREAT_REPORT_FILENAME,
    settings,
)


class UploadError(Exception):
    """Raised when an upload fails validation."""


# ---------- Validation ----------

def validate_csv_bytes(dataset: str, raw_bytes: bytes) -> pd.DataFrame:
    """
    Parse raw bytes as a CSV and validate the schema.

    Returns the parsed DataFrame on success.
    Raises UploadError with a useful message on failure.
    """
    if dataset not in DATASET_SCHEMAS:
        raise UploadError(
            f"Unknown dataset '{dataset}'. Valid: {sorted(DATASET_SCHEMAS.keys())}"
        )

    # Size guard
    size_mb = len(raw_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise UploadError(
            f"File too large: {size_mb:.1f} MB (limit: {settings.MAX_UPLOAD_SIZE_MB} MB)"
        )

    # Parse
    try:
        df = pd.read_csv(StringIO(raw_bytes.decode("utf-8")))
    except UnicodeDecodeError:
        raise UploadError("File is not valid UTF-8 text.")
    except pd.errors.EmptyDataError:
        raise UploadError("File is empty or has no parseable rows.")
    except pd.errors.ParserError as e:
        raise UploadError(f"CSV parse error: {e}")

    # Column check
    required = DATASET_SCHEMAS[dataset]["required_columns"]
    actual = set(df.columns)
    missing = required - actual
    if missing:
        raise UploadError(
            f"Missing required columns for '{dataset}': {sorted(missing)}. "
            f"Got columns: {sorted(actual)}"
        )

    # Row count sanity
    if len(df) == 0:
        raise UploadError("CSV has headers but no data rows.")

    return df


def validate_threat_report_bytes(raw_bytes: bytes) -> str:
    """Validate the markdown threat report. Returns decoded text on success."""
    size_mb = len(raw_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise UploadError(
            f"File too large: {size_mb:.1f} MB (limit: {settings.MAX_UPLOAD_SIZE_MB} MB)"
        )
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise UploadError("Threat report is not valid UTF-8 text.")
    if not text.strip():
        raise UploadError("Threat report is empty.")
    return text


# ---------- Atomic write ----------

def _timestamp() -> str:
    """Filesystem-safe ISO-ish timestamp."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def _backup_existing(target: Path) -> Path | None:
    """If `target` exists, move it to data/backups/ with a timestamp. Return new path or None."""
    if not target.exists():
        return None
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_name = f"{target.name}.bak-{_timestamp()}"
    backup_path = settings.BACKUP_DIR / backup_name
    shutil.move(str(target), str(backup_path))
    return backup_path


def _prune_backups(filename: str) -> int:
    """Keep only the last N backups for this filename. Return number deleted."""
    prefix = f"{filename}.bak-"
    backups = sorted(
        [p for p in settings.BACKUP_DIR.glob(f"{prefix}*")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    to_delete = backups[settings.BACKUP_RETENTION_COUNT:]
    for p in to_delete:
        p.unlink(missing_ok=True)
    return len(to_delete)


def write_csv_atomic(dataset: str, raw_bytes: bytes) -> dict:
    """
    Validated + atomic write of an uploaded CSV.

    Flow:
        1. Validate bytes → DataFrame
        2. Stage to data/raw/<filename>.tmp
        3. Backup existing data/raw/<filename> → data/backups/
        4. Rename .tmp → final
        5. Prune old backups

    Returns metadata dict for the API response.
    """
    df = validate_csv_bytes(dataset, raw_bytes)

    filename = DATASET_SCHEMAS[dataset]["filename"]
    target = settings.RAW_DATA_DIR / filename
    staging = settings.RAW_DATA_DIR / f"{filename}.tmp"

    settings.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(staging, index=False)

    backup_path = _backup_existing(target)
    staging.replace(target)  # atomic on POSIX

    pruned = _prune_backups(filename)

    return {
        "dataset": dataset,
        "filename": filename,
        "rows_written": len(df),
        "columns": list(df.columns),
        "backup_created": str(backup_path.name) if backup_path else None,
        "old_backups_pruned": pruned,
    }


def write_threat_report_atomic(raw_bytes: bytes) -> dict:
    """Validated + atomic write of the markdown threat report."""
    text = validate_threat_report_bytes(raw_bytes)

    target = settings.RAW_DATA_DIR / THREAT_REPORT_FILENAME
    staging = settings.RAW_DATA_DIR / f"{THREAT_REPORT_FILENAME}.tmp"

    settings.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    staging.write_text(text, encoding="utf-8")

    backup_path = _backup_existing(target)
    staging.replace(target)

    pruned = _prune_backups(THREAT_REPORT_FILENAME)

    return {
        "filename": THREAT_REPORT_FILENAME,
        "size_bytes": len(raw_bytes),
        "backup_created": str(backup_path.name) if backup_path else None,
        "old_backups_pruned": pruned,
    }


# ---------- Status ----------

def get_data_status() -> dict:
    """Inspect data/raw/ and report what's loaded."""
    status = {"datasets": [], "threat_report": None}

    for dataset, spec in DATASET_SCHEMAS.items():
        path = settings.RAW_DATA_DIR / spec["filename"]
        if path.exists():
            stat = path.stat()
            try:
                row_count = sum(1 for _ in open(path, encoding="utf-8")) - 1
            except Exception:
                row_count = -1
            status["datasets"].append({
                "dataset": dataset,
                "filename": spec["filename"],
                "present": True,
                "rows": row_count,
                "size_bytes": stat.st_size,
                "last_modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            })
        else:
            status["datasets"].append({
                "dataset": dataset,
                "filename": spec["filename"],
                "present": False,
                "rows": 0,
                "size_bytes": 0,
                "last_modified": None,
            })

    report_path = settings.RAW_DATA_DIR / THREAT_REPORT_FILENAME
    if report_path.exists():
        stat = report_path.stat()
        status["threat_report"] = {
            "filename": THREAT_REPORT_FILENAME,
            "present": True,
            "size_bytes": stat.st_size,
            "last_modified": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
        }
    else:
        status["threat_report"] = {
            "filename": THREAT_REPORT_FILENAME,
            "present": False,
            "size_bytes": 0,
            "last_modified": None,
        }

    return status
