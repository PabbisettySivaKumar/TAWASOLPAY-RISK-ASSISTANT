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

import pandas as pd

from src.config import settings


@dataclass
class DataBundle:
    """Container for all loaded datasets."""
    assets: pd.DataFrame
    vulnerabilities: pd.DataFrame
    threat_intelligence: pd.DataFrame
    business_services: pd.DataFrame
    remediation_hints: pd.DataFrame
    threat_report: str


def load_all() -> DataBundle:
    """Load every file from data/raw/ and return as a DataBundle."""
    # TODO: implement
    raise NotImplementedError


def join_vulns_with_assets(
    vulnerabilities: pd.DataFrame,
    assets: pd.DataFrame,
) -> pd.DataFrame:
    """Join vulnerabilities -> assets so each vuln carries asset context."""
    # TODO: implement (left join on asset_id)
    raise NotImplementedError


def match_threat_intel_to_cves(
    vulnerabilities: pd.DataFrame,
    threat_intel: pd.DataFrame,
) -> pd.DataFrame:
    """
    Match the 25 real threat-intel records to CVEs in our environment.
    The 15 noise records will naturally not match.
    """
    # TODO: implement (inner join on cve_id)
    raise NotImplementedError
