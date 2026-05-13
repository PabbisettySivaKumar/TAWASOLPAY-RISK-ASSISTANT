"""
Load TawasolPay's data pack from data/raw/.

Loads 5 CSVs + 1 markdown threat report and joins them into a coherent
in-memory dataset.

Files expected:
    assets.csv
    vulnerabilities.csv
    threat_intelligence.csv
    business_services.csv
    remediation_guidance.csv          (the "trap" CSV — used as a hint only)
    synthetic_threat_report.md
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import DATASET_SCHEMAS, THREAT_REPORT_FILENAME, settings


# Columns that should be coerced to real Python booleans.
# CSVs commonly arrive with "Yes"/"No", "True"/"False", "1"/"0" etc.
BOOLEAN_COLUMNS: dict[str, set[str]] = {
    "assets": {"internet_exposed", "edr_installed"},
    "vulnerabilities": {"exploit_available", "patch_available", "auth_required"},
    "business_services": {"customer_facing"},
    "threat_intelligence": {"ransomware_association"},
    "remediation_guidance": set(),
}


@dataclass
class DataBundle:
    """Container for all loaded datasets."""
    assets: pd.DataFrame
    vulnerabilities: pd.DataFrame
    threat_intelligence: pd.DataFrame
    business_services: pd.DataFrame
    remediation_hints: pd.DataFrame
    threat_report: str


# ---------- Public API ----------

def load_all() -> DataBundle:
    """Load every file from data/raw/ and return as a DataBundle."""
    return DataBundle(
        assets=_load_csv("assets"),
        vulnerabilities=_load_csv("vulnerabilities"),
        threat_intelligence=_load_csv("threat_intelligence"),
        business_services=_load_csv("business_services"),
        remediation_hints=_load_csv("remediation_guidance"),
        threat_report=_load_threat_report(),
    )


def join_vulns_with_assets(
    vulnerabilities: pd.DataFrame,
    assets: pd.DataFrame,
) -> pd.DataFrame:
    """Left join vulnerabilities -> assets so each vuln carries asset context."""
    return vulnerabilities.merge(
        assets,
        on="asset_id",
        how="left",
        suffixes=("", "_asset"),
    )


def match_threat_intel_to_cves(
    vulnerabilities: pd.DataFrame,
    threat_intel: pd.DataFrame,
) -> pd.DataFrame:
    """
    Filter threat_intel to records that:
      (a) reference a CVE (not a NIST control ID), AND
      (b) match a CVE present in our vulnerabilities table.

    The `matched_cve_or_control` column is polymorphic — it can hold either
    a CVE id (CVE-2024-1234) or a control id (AC-2). We only care about CVE
    matches here. The 15 noise records in the data pack naturally fall away.

    Returns the filtered threat_intel rows with `matched_cve_or_control`
    renamed to `cve` for easy joining downstream.
    """
    if threat_intel.empty or vulnerabilities.empty:
        return threat_intel.iloc[0:0].copy()

    ti = threat_intel.copy()
    matched_col = ti["matched_cve_or_control"].astype(str).str.upper()
    ti = ti[matched_col.str.startswith("CVE-")].copy()
    ti = ti.rename(columns={"matched_cve_or_control": "cve"})
    ti["cve"] = ti["cve"].astype(str).str.upper()

    our_cves = set(vulnerabilities["cve"].dropna().astype(str).str.upper())
    ti = ti[ti["cve"].isin(our_cves)]

    return ti.reset_index(drop=True)


# ---------- Internals ----------

def _load_csv(dataset: str) -> pd.DataFrame:
    """Read one assignment CSV, validate its schema, and normalize types."""
    spec = DATASET_SCHEMAS[dataset]
    path: Path = settings.RAW_DATA_DIR / spec["filename"]

    if not path.exists():
        raise FileNotFoundError(
            f"Missing {dataset} CSV at {path}. "
            f"Upload it via POST /data/upload/{dataset} or drop it in data/raw/."
        )

    df = pd.read_csv(path)
    _validate_schema(df, dataset, spec["required_columns"])
    df = _strip_string_columns(df)
    df = _coerce_booleans(df, BOOLEAN_COLUMNS.get(dataset, set()))
    return df


def _validate_schema(df: pd.DataFrame, dataset: str, required: set[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"{dataset}.csv is missing required columns: {sorted(missing)}. "
            f"Got: {sorted(df.columns)}"
        )


def _strip_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        df.loc[df[col].isin({"nan", "None", ""}), col] = pd.NA
    return df


def _coerce_booleans(df: pd.DataFrame, columns: set[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = df[col].map(_to_bool)
    return df


def _to_bool(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "1", "y", "t"}


def _load_threat_report() -> str:
    path = settings.RAW_DATA_DIR / THREAT_REPORT_FILENAME
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
