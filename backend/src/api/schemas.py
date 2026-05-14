"""
Pydantic schemas for API request / response bodies.

These define the JSON shape the API exposes. Frontend (later) and any
API consumer will see these in the auto-generated OpenAPI docs.
"""

from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., example="ok")
    version: str = Field(..., example="0.1.0")


class ThreatIntelMatch(BaseModel):
    """A matched threat intel record for a given CVE."""
    actor: str
    campaign: str
    target_sector: str
    ransomware_associated: bool


class NistControl(BaseModel):
    """A retrieved NIST 800-53 control snippet."""
    control_id: str = Field(..., example="SI-2")
    control_name: str = Field(..., example="Flaw Remediation")
    excerpt: str = Field(..., description="Retrieved text from NIST 800-53 Rev. 5")
    similarity_score: float = Field(..., description="Cosine similarity from vector retrieval")


class RiskEntry(BaseModel):
    """One ranked risk in the top-5 list."""
    risk_id: str
    rank: int
    risk_score: float
    asset_id: str
    asset_name: str
    asset_environment: str
    cve_id: str
    cvss: float
    internet_exposed: bool
    active_exploit: bool
    business_service: str
    threat_intel: Optional[ThreatIntelMatch] = None
    nist_controls: list[NistControl]
    explanation: str = Field(..., description="Plain-English reason this ranks here")


class RiskListResponse(BaseModel):
    """Top-5 risks payload."""
    risks: list[RiskEntry]
    generated_at: str


class RiskDetail(RiskEntry):
    """Same shape as RiskEntry plus extended fields if needed later."""
    pass


class RefreshResponse(BaseModel):
    success: bool
    message: str
    assets_loaded: int
    vulnerabilities_loaded: int
    threat_intel_loaded: int
    nist_chunks_indexed: int


# ---------- Upload schemas ----------

class UploadResult(BaseModel):
    """Outcome of a single file upload."""
    dataset: str
    filename: str
    rows_written: Optional[int] = None
    size_bytes: Optional[int] = None
    columns: Optional[list[str]] = None
    backup_created: Optional[str] = None
    old_backups_pruned: int = 0


class UploadResponse(BaseModel):
    """Response for a single-file upload."""
    success: bool
    message: str
    result: UploadResult


class BatchUploadResponse(BaseModel):
    """Response for a batch upload of all 5 CSVs + threat report."""
    success: bool
    message: str
    results: list[UploadResult]
    failed: list[dict] = Field(
        default_factory=list,
        description="Datasets that failed validation, with their error message",
    )


class ClearedItem(BaseModel):
    dataset: str
    filename: str
    backup_created: Optional[str] = None


class ClearResponse(BaseModel):
    """Outcome of clearing all uploaded files."""
    success: bool
    message: str
    cleared_count: int
    cleared: list[ClearedItem]
    already_absent: list[str]


class DatasetStatus(BaseModel):
    dataset: str
    filename: str
    present: bool
    rows: int
    size_bytes: int
    last_modified: Optional[str]


class ThreatReportStatus(BaseModel):
    filename: str
    present: bool
    size_bytes: int
    last_modified: Optional[str]


class DataStatusResponse(BaseModel):
    """Snapshot of what's currently in data/raw/."""
    datasets: list[DatasetStatus]
    threat_report: ThreatReportStatus


# ---------- External data refresh schemas ----------

class ExternalSourceStatus(BaseModel):
    """Status of one external data source on disk."""
    filename: str
    present: bool
    size_bytes: int
    last_modified: Optional[str]
    age_hours: Optional[float]
    rows: Optional[int] = None


class ExternalDataStatusResponse(BaseModel):
    """Status of both external data sources."""
    kev: ExternalSourceStatus
    nist: ExternalSourceStatus


class RefreshSourceResult(BaseModel):
    """Outcome of refreshing one external source. Fields vary by source/state."""
    success: bool
    source: str
    filename: Optional[str] = None
    rows_downloaded: Optional[int] = None
    previous_size_bytes: Optional[int] = None
    new_size_bytes: Optional[int] = None
    vector_store_rebuilt: Optional[bool] = None
    chunks_indexed: Optional[int] = None
    downloaded_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    stage: Optional[str] = None
    error: Optional[str] = None
    note: Optional[str] = None


class RefreshAllResponse(BaseModel):
    """Result of refreshing both sources."""
    success: bool
    kev: RefreshSourceResult
    nist: RefreshSourceResult
    duration_seconds: float