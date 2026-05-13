"""Sanity tests for the risk scoring engine."""

import pytest

from src.scoring.risk_engine import (
    _cvss_signal,
    _exposure_signal,
    _exploit_signal,
    _threat_intel_signal,
    _criticality_signal,
    _missing_controls_signal,
)


def test_cvss_signal_normalizes_to_unit_range():
    assert _cvss_signal(0) == 0.0
    assert _cvss_signal(5) == 0.5
    assert _cvss_signal(10) == 1.0
    assert _cvss_signal(11) == 1.0  # clamped


def test_exposure_signal_is_binary():
    assert _exposure_signal(True) == 1.0
    assert _exposure_signal(False) == 0.0


def test_exploit_signal_prefers_kev_plus_exploit():
    assert _exploit_signal(True, True) == 1.0
    assert _exploit_signal(False, True) == 0.7
    assert _exploit_signal(True, False) == 0.5
    assert _exploit_signal(False, False) == 0.0


def test_threat_intel_signal_prefers_ransomware():
    assert _threat_intel_signal(True, True) == 1.0
    assert _threat_intel_signal(True, False) == 0.6
    assert _threat_intel_signal(False, False) == 0.0


def test_criticality_signal_maps_levels():
    assert _criticality_signal("critical") == 1.0
    assert _criticality_signal("high") == 0.75
    assert _criticality_signal("medium") == 0.5
    assert _criticality_signal("low") == 0.25
    assert _criticality_signal("unknown") == 0.5  # default


def test_missing_controls_signal_inverts_edr():
    assert _missing_controls_signal(edr_installed=False) == 1.0
    assert _missing_controls_signal(edr_installed=True) == 0.0
