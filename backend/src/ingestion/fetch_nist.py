"""
Fetch the NIST SP 800-53 Rev. 5 security controls catalog.

The catalog contains ~1,000 controls. We download once and chunk for RAG.
The retrieved chunks become the remediation guidance for each ranked risk.

Source: https://csrc.nist.gov/projects/risk-management/sp800-53-controls/downloads
Format: CSV (the "catalog_load" derivative from NIST). One row per control.

Typical columns in the NIST CSV (confirm after first download):
    Control Identifier              e.g. "SI-2"
    Control (or Control Enhancement) Name   e.g. "Flaw Remediation"
    Control Text                    the normative statement
    Discussion                      explanatory prose
    Related Controls                comma-separated control IDs

We treat Control Text + Discussion as the embedding payload.
"""

from pathlib import Path

import pandas as pd
import requests

from src.config import settings

NIST_LOCAL_PATH = settings.REFERENCE_DATA_DIR / "nist_800_53.csv"


def download_nist() -> Path:
    """Download the NIST 800-53 catalog CSV and save to data/reference/."""
    settings.REFERENCE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(settings.NIST_800_53_URL, timeout=60)
    response.raise_for_status()
    NIST_LOCAL_PATH.write_bytes(response.content)
    return NIST_LOCAL_PATH


FAMILY_NAMES: dict[str, str] = {
    "AC": "Access Control",
    "AT": "Awareness and Training",
    "AU": "Audit and Accountability",
    "CA": "Assessment, Authorization, and Monitoring",
    "CM": "Configuration Management",
    "CP": "Contingency Planning",
    "IA": "Identification and Authentication",
    "IR": "Incident Response",
    "MA": "Maintenance",
    "MP": "Media Protection",
    "PE": "Physical and Environmental Protection",
    "PL": "Planning",
    "PM": "Program Management",
    "PS": "Personnel Security",
    "PT": "PII Processing and Transparency",
    "RA": "Risk Assessment",
    "SA": "System and Services Acquisition",
    "SC": "System and Communications Protection",
    "SI": "System and Information Integrity",
    "SR": "Supply Chain Risk Management",
}


def load_nist_controls() -> list[dict]:
    """
    Load the NIST controls CSV and return a list of dicts.

    Each dict has clean keys:
        id          e.g. "SI-2"
        name        e.g. "Flaw Remediation"
        statement   the normative control text
        discussion  explanatory prose
        related     comma-separated related control ids
        family      e.g. "SI" -> "System and Information Integrity"
    """
    if not NIST_LOCAL_PATH.exists():
        raise FileNotFoundError(
            f"{NIST_LOCAL_PATH} not found. Run download_nist() first."
        )

    df = pd.read_csv(NIST_LOCAL_PATH)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

    out: list[dict] = []
    for _, row in df.iterrows():
        identifier = str(row.get("identifier", "")).strip()
        if not identifier:
            continue
        family_prefix = identifier.split("-", 1)[0]
        out.append({
            "id": identifier,
            "name": _clean(row.get("name")),
            "statement": _clean(row.get("control_text")),
            "discussion": _clean(row.get("discussion")),
            "related": _clean(row.get("related")),
            "family": FAMILY_NAMES.get(family_prefix, family_prefix),
        })
    return out


def _clean(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() in {"nan", "none"} else s