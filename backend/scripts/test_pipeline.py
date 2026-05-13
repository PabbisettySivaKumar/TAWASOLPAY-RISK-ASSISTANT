"""
Run the pipeline directly from the command line, no HTTP server.
Useful for debugging without the FastAPI layer in the way.

Usage:
    python scripts/test_pipeline.py
"""

from src.pipeline.orchestrator import run_pipeline


def main() -> None:
    response = run_pipeline()
    for risk in response.risks:
        print(f"\n#{risk.rank}  score={risk.risk_score:.1f}  {risk.cve_id} on {risk.asset_name}")
        print(f"  Service : {risk.business_service}")
        print(f"  NIST    : {', '.join(c.control_id for c in risk.nist_controls)}")
        print(f"  Why     : {risk.explanation}")


if __name__ == "__main__":
    main()
