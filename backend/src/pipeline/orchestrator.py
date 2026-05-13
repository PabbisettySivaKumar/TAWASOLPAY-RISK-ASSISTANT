"""
End-to-end pipeline.

Flow:
    1. Load CSVs + threat report                    (ingestion.load_data)
    2. Load CISA KEV                                (ingestion.fetch_kev)
    3. Score every vulnerability                    (scoring.risk_engine)
    4. Take top 5                                   (scoring.risk_engine)
    5. For each: retrieve NIST controls             (rag.retriever)
    6. For each: generate plain-English explanation (llm.llm_client)
    7. Format and return                            (output.formatter)

This is the function the FastAPI route calls.
"""

from src.api.schemas import RiskListResponse


def run_pipeline() -> RiskListResponse:
    """Run the full pipeline end-to-end and return the API response."""
    # TODO: implement once individual modules are filled in
    raise NotImplementedError
