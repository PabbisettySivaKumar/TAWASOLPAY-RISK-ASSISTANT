"""
Fetch the CISA Known Exploited Vulnerabilities (KEV) catalog.

Used to cross-reference CVEs in vulnerabilities.csv and confirm whether
each is actively exploited in the wild (and whether it's associated with
known ransomware campaigns).

Source: https://github.com/cisagov/kev-data (GitHub mirror maintained by CISA).
Format: CSV, updated on US business days.

Key fields per the assignment:
    cveID                            e.g. "CVE-2023-1234"
    knownRansomwareCampaignUse       "Known" | "Unknown"
    dateAdded                        ISO date the CVE was added to KEV
    requiredAction                   the action CISA recommends
"""

from pathlib import Path

import pandas as pd
import requests

from src.config import settings

KEV_LOCAL_PATH = settings.REFERENCE_DATA_DIR / "cisa_kev.csv"


def download_kev() -> Path:
    """Download the latest CISA KEV CSV from the GitHub mirror."""
    settings.REFERENCE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(settings.CISA_KEV_URL, timeout=60)
    response.raise_for_status()
    KEV_LOCAL_PATH.write_bytes(response.content)
    return KEV_LOCAL_PATH


def load_kev_local() -> pd.DataFrame:
    """Load the saved CISA KEV CSV as a DataFrame."""
    if not KEV_LOCAL_PATH.exists():
        raise FileNotFoundError(
            f"KEV CSV not found at {KEV_LOCAL_PATH}. "
            f"Run `python scripts/setup_data.py` first."
        )
    return pd.read_csv(KEV_LOCAL_PATH)


def is_in_kev(cve_id: str, kev_df: pd.DataFrame) -> bool:
    """Return True if the CVE appears anywhere in the KEV catalog."""
    return bool((kev_df["cveID"] == cve_id).any())


def is_known_ransomware_cve(cve_id: str, kev_df: pd.DataFrame) -> bool:
    """Return True if the CVE is in KEV AND tagged as ransomware-associated."""
    matches = kev_df[kev_df["cveID"] == cve_id]
    if matches.empty:
        return False
    return bool((matches["knownRansomwareCampaignUse"] == "Known").any())


def get_kev_record(cve_id: str, kev_df: pd.DataFrame) -> dict | None:
    """Return the full KEV record for a CVE, or None if not in KEV."""
    matches = kev_df[kev_df["cveID"] == cve_id]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()