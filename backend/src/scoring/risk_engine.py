"""
Multi-signal risk scoring engine.

Computes a composite risk score for each vulnerability that combines:
    - CVSS technical severity                       (weight from config)
    - Internet exposure of the asset                (weight from config)
    - Active exploit availability                   (weight from config)
    - Threat actor / campaign match for the CVE     (weight from config)
    - Business service criticality                  (weight from config)
    - Missing compensating controls (e.g. no EDR)   (weight from config)

The score is normalized to 0..100. Top 5 highest are returned.

Why not just CVSS:
    A CVSS 10 on an internal dev box should NOT outrank a CVSS 8 on the
    internet-exposed payment gateway with an active ransomware campaign
    pointing at it. This scoring captures that.
"""

from dataclasses import dataclass

import pandas as pd

from src.config import settings


@dataclass
class ScoredRisk:
    """A scored, ranked risk."""
    risk_id: str
    score: float
    asset_id: str
    cve_id: str
    score_breakdown: dict  # contribution of each signal — used for the explanation


def score_all_risks(
    vulnerabilities: pd.DataFrame,
    assets: pd.DataFrame,
    threat_intel: pd.DataFrame,
    business_services: pd.DataFrame,
    kev_df: pd.DataFrame,
) -> list[ScoredRisk]:
    """Score every vulnerability and return them sorted high-to-low."""
    # TODO: implement
    raise NotImplementedError


def get_top_n(scored: list[ScoredRisk], n: int = 5) -> list[ScoredRisk]:
    """Return the top-N risks."""
    return sorted(scored, key=lambda r: r.score, reverse=True)[:n]


# ---------- Individual signal calculators ----------
# Each returns a 0..1 contribution that gets multiplied by the weight.

def _cvss_signal(cvss: float) -> float:
    """Normalize CVSS (0-10) to 0..1."""
    return min(max(cvss / 10.0, 0.0), 1.0)


def _exposure_signal(internet_exposed: bool) -> float:
    return 1.0 if internet_exposed else 0.0


def _exploit_signal(exploit_available: bool, in_kev: bool) -> float:
    """1.0 if both exploit + in KEV, 0.7 if just exploit, 0.5 if just KEV, 0 else."""
    if exploit_available and in_kev:
        return 1.0
    if in_kev:
        return 0.7
    if exploit_available:
        return 0.5
    return 0.0


def _threat_intel_signal(matched: bool, ransomware: bool) -> float:
    if matched and ransomware:
        return 1.0
    if matched:
        return 0.6
    return 0.0


def _criticality_signal(criticality: str) -> float:
    mapping = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}
    return mapping.get(criticality.lower(), 0.5)


def _missing_controls_signal(edr_installed: bool) -> float:
    return 1.0 if not edr_installed else 0.0
