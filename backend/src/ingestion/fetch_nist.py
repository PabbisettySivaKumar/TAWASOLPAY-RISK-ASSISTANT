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


def load_nist_controls() -> list[dict]:
    """
    Load the NIST controls CSV and return a list of dicts.

    Each dict will have clean keys: id, name, statement, discussion, related, family.
    Column names in the source CSV are mapped to these clean keys.
    """
    # TODO: parse the downloaded CSV with pd.read_csv,
    # rename columns to clean keys, return as list of dicts.
    # Exact column names confirmed on first run of setup_data.py.
    raise NotImplementedError