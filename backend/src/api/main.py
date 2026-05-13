"""
FastAPI application entry point.

Exposes:
    GET  /                              — health check
    GET  /risks/top                     — top 5 ranked risks
    GET  /risks/{risk_id}               — single risk detail
    POST /data/refresh                  — reload caches + rerun pipeline
    GET  /data/status                   — what's currently in data/raw/
    POST /data/upload/{dataset}         — replace a single CSV (Scenario A)
    POST /data/upload/threat-report     — replace the threat report
    POST /data/upload/batch             — replace all 5 CSVs at once (Scenario C)
    GET  /docs                          — Swagger UI (auto-generated)

Run locally:
    uvicorn src.api.main:app --reload --port 8000
"""

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.api.dependencies import invalidate_data_caches
from src.api.schemas import (
    BatchUploadResponse,
    DataStatusResponse,
    HealthResponse,
    RefreshResponse,
    RiskDetail,
    RiskListResponse,
    UploadResponse,
    UploadResult,
)
from src.api.upload import (
    DATASET_SCHEMAS,
    UploadError,
    get_data_status,
    write_csv_atomic,
    write_threat_report_atomic,
)

app = FastAPI(
    title="TawasolPay Risk Assistant",
    description="AI-powered cyber risk prioritization with NIST 800-53 grounded remediation.",
    version="0.1.0",
)

# CORS — allow any origin for the demo (frontend will be on a different domain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
#  Health
# ============================================================

@app.get("/", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Health check + minimal system info."""
    return HealthResponse(status="ok", version="0.1.0")


# ============================================================
#  Risks
# ============================================================

@app.get("/risks/top", response_model=RiskListResponse, tags=["risks"])
async def get_top_risks() -> RiskListResponse:
    """Return the top 5 ranked risks with evidence and NIST remediation guidance."""
    # TODO: call src.pipeline.orchestrator.run_pipeline()
    raise HTTPException(status_code=501, detail="Not implemented yet")


@app.get("/risks/{risk_id}", response_model=RiskDetail, tags=["risks"])
async def get_risk_detail(risk_id: str) -> RiskDetail:
    """Return details for a single risk by ID."""
    # TODO: look up risk_id in cached pipeline output
    raise HTTPException(status_code=501, detail="Not implemented yet")


# ============================================================
#  Data management
# ============================================================

@app.get("/data/status", response_model=DataStatusResponse, tags=["data"])
async def data_status() -> DataStatusResponse:
    """Show what data is currently loaded in data/raw/."""
    return DataStatusResponse(**get_data_status())


@app.post("/data/refresh", response_model=RefreshResponse, tags=["data"])
async def refresh_data() -> RefreshResponse:
    """Force a reload of cached CSVs + rebuild the vector store."""
    # TODO: invalidate_data_caches(), then rebuild vector store + rerun pipeline
    raise HTTPException(status_code=501, detail="Not implemented yet")


# NOTE: Route ORDER MATTERS in FastAPI.
# Static paths (/batch, /threat-report) MUST be declared BEFORE the dynamic
# path (/{dataset}). Otherwise FastAPI matches the dynamic route first and
# treats "batch" or "threat-report" as a dataset name.


# ---------- Upload: batch (Scenario C) ----------

@app.post("/data/upload/batch", response_model=BatchUploadResponse, tags=["data"])
async def upload_batch(
    assets: UploadFile = File(...),
    vulnerabilities: UploadFile = File(...),
    threat_intelligence: UploadFile = File(...),
    business_services: UploadFile = File(...),
    remediation_guidance: UploadFile = File(...),
    threat_report: UploadFile | None = File(None),
) -> BatchUploadResponse:
    """
    Replace all 5 CSVs (and optionally the threat report) in one call.

    Validation is per-file. If any file fails validation, that file is rejected
    BUT the others still write — this is intentional so a single bad file
    doesn't block your morning refresh. Failed files appear in `failed[]`.

    If you'd prefer all-or-nothing atomicity, tell me and we'll switch the
    semantics (validate all first, then write all).
    """
    uploads = {
        "assets": assets,
        "vulnerabilities": vulnerabilities,
        "threat_intelligence": threat_intelligence,
        "business_services": business_services,
        "remediation_guidance": remediation_guidance,
    }

    results: list[UploadResult] = []
    failed: list[dict] = []

    for dataset, upload_file in uploads.items():
        raw_bytes = await upload_file.read()
        try:
            result_dict = write_csv_atomic(dataset, raw_bytes)
            results.append(UploadResult(**result_dict))
        except UploadError as e:
            failed.append({"dataset": dataset, "error": str(e)})

    if threat_report is not None:
        raw_bytes = await threat_report.read()
        try:
            result_dict = write_threat_report_atomic(raw_bytes)
            results.append(UploadResult(
                dataset="threat_report",
                filename=result_dict["filename"],
                size_bytes=result_dict["size_bytes"],
                backup_created=result_dict["backup_created"],
                old_backups_pruned=result_dict["old_backups_pruned"],
            ))
        except UploadError as e:
            failed.append({"dataset": "threat_report", "error": str(e)})

    if results:
        invalidate_data_caches()

    success = len(failed) == 0
    message = (
        f"Batch upload complete. {len(results)} files written, {len(failed)} failed."
    )

    return BatchUploadResponse(
        success=success,
        message=message,
        results=results,
        failed=failed,
    )


# ---------- Upload: threat report ----------

@app.post("/data/upload/threat-report", response_model=UploadResponse, tags=["data"])
async def upload_threat_report(file: UploadFile = File(...)) -> UploadResponse:
    """Replace the markdown threat report in data/raw/."""
    raw_bytes = await file.read()

    try:
        result_dict = write_threat_report_atomic(raw_bytes)
    except UploadError as e:
        raise HTTPException(status_code=400, detail=str(e))

    invalidate_data_caches()

    return UploadResponse(
        success=True,
        message="Threat report replaced.",
        result=UploadResult(
            dataset="threat_report",
            filename=result_dict["filename"],
            size_bytes=result_dict["size_bytes"],
            backup_created=result_dict["backup_created"],
            old_backups_pruned=result_dict["old_backups_pruned"],
        ),
    )


# ---------- Upload: single CSV (Scenario A) — MUST come AFTER static routes ----------

@app.post("/data/upload/{dataset}", response_model=UploadResponse, tags=["data"])
async def upload_single_csv(dataset: str, file: UploadFile = File(...)) -> UploadResponse:
    """
    Replace one CSV in data/raw/ with an uploaded file.

    Path parameter `dataset` must be one of:
        assets, vulnerabilities, threat_intelligence,
        business_services, remediation_guidance

    The previous version (if any) is auto-backed-up to data/backups/.
    Caches are invalidated so the next /risks/top request sees fresh data.
    """
    if dataset not in DATASET_SCHEMAS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown dataset '{dataset}'. Valid: {sorted(DATASET_SCHEMAS.keys())}",
        )

    raw_bytes = await file.read()

    try:
        result_dict = write_csv_atomic(dataset, raw_bytes)
    except UploadError as e:
        raise HTTPException(status_code=400, detail=str(e))

    invalidate_data_caches()

    return UploadResponse(
        success=True,
        message=f"{dataset} replaced. {result_dict['rows_written']} rows written.",
        result=UploadResult(**result_dict),
    )