"""
Central configuration for the backend.

Loads from environment variables (and .env file) via pydantic-settings.
Every other module imports `settings` from here — no hard-coded paths,
no scattered os.getenv() calls.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root = backend/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env."""

    # ---------- LLM ----------
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    LLM_PRIMARY_MODEL: str = "groq/llama-3.3-70b-versatile"
    LLM_FALLBACK_MODEL: str = ""

    # ---------- Embeddings ----------
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ---------- Paths ----------
    DATA_DIR: Path = PROJECT_ROOT / "data"
    RAW_DATA_DIR: Path = PROJECT_ROOT / "data" / "raw"
    REFERENCE_DATA_DIR: Path = PROJECT_ROOT / "data" / "reference"
    CHROMA_DB_DIR: Path = PROJECT_ROOT / "data" / "chroma_db"
    BACKUP_DIR: Path = PROJECT_ROOT / "data" / "backups"

    # ---------- Upload settings ----------
    MAX_UPLOAD_SIZE_MB: int = 50
    BACKUP_RETENTION_COUNT: int = 5  # keep last N backups per dataset

    # ---------- External data sources ----------
    # CISA KEV — GitHub mirror specified in the assignment.
    # The assignment points to https://github.com/cisagov/kev-data.
    # We use the raw CSV from the develop branch (the repo's default branch).
    # Update schedule: weekdays during US business hours, synced within minutes of cisa.gov.
    CISA_KEV_URL: str = "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.csv"

    # NIST SP 800-53 Rev. 5 (v5.1) — official CSV derivative format from CSRC
    # Source page: https://csrc.nist.gov/projects/risk-management/sp800-53-controls/downloads
    NIST_800_53_URL: str = "https://csrc.nist.gov/CSRC/media/Projects/risk-management/800-53%20Downloads/800-53r5/NIST_SP-800-53_rev5_catalog_load.csv"

    # ---------- Server ----------
    BACKEND_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # ---------- Auth ----------
    # If set, refresh endpoints require X-API-Key matching this value.
    # If empty, refresh endpoints are open (good for local dev).
    API_KEY: str = ""

    # ---------- External refresh ----------
    # Minimum seconds between refreshes of the same source.
    REFRESH_COOLDOWN_SECONDS: int = 300  # 5 minutes

    # ---------- RAG settings ----------
    CHUNK_SIZE: int = 500           # characters per chunk
    CHUNK_OVERLAP: int = 50
    TOP_K_RETRIEVAL: int = 3        # how many NIST chunks to retrieve per risk

    # ---------- Risk scoring weights ----------
    # These will be used by src/scoring/risk_engine.py
    WEIGHT_CVSS: float = 0.25
    WEIGHT_INTERNET_EXPOSURE: float = 0.20
    WEIGHT_ACTIVE_EXPLOIT: float = 0.15
    WEIGHT_THREAT_INTEL_MATCH: float = 0.20
    WEIGHT_BUSINESS_CRITICALITY: float = 0.15
    WEIGHT_MISSING_CONTROLS: float = 0.05

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()


# ---------------------------------------------------------------
# Dataset registry — what we accept for upload
# ---------------------------------------------------------------
# Each entry defines: filename on disk + the REQUIRED columns
# (extra columns are allowed; missing required columns reject the upload).
# Update this when the data pack schema changes.
#
# NOTE: column names below are placeholders based on the assignment brief.
# Adjust to the real headers once you inspect the actual CSVs.

DATASET_SCHEMAS: dict[str, dict] = {
    "assets": {
        "filename": "assets.csv",
        "required_columns": {
            "asset_id", "asset_name", "asset_type", "environment",
            "owner_team", "business_service", "internet_exposed",
            "criticality", "data_classification","edr_installed","last_seen_days","location", "vendor_product",
        },
    },
    "vulnerabilities": {
        "filename": "vulnerabilities.csv",
        "required_columns": {
            "vuln_id", "asset_id", "vulnerability_name","cve", "severity", "cvss",
            "exploit_available", "patch_available", "days_open", "asset_exposure", "auth_required", "status", "affected_component",
        },
    },
    "threat_intelligence": {
        "filename": "threat_intelligence.csv",
        "required_columns": {
            "intel_id", "threat_actor", "campaign_name", "target_sector",
            "target_region", "matched_cve_or_control", "exploit_maturity", "active_last_seen", "ransomware_association", "confidence", "summary",
        },
    },
    "business_services": {
        "filename": "business_services.csv",
        "required_columns": {
            "business_service", "business_owner", "business_impact",
            "customer_facing", "compliance_scope", "revenue_impact", "rto_hours", "depends_on", "risk_appetite",
        },
    },
    "remediation_guidance": {
        "filename": "remediation_guidance.csv",
        "required_columns": {"finding_type", "recommended_action", "priority_hint", "validation_evidence"},
    },
}

THREAT_REPORT_FILENAME = "synthetic_threat_report.md"
