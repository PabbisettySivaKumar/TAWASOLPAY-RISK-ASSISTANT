# `data/raw/`

Drop the assignment data pack here. The system expects exactly these files:

| File | Description |
|---|---|
| `assets.csv` | 60 rows — asset inventory |
| `vulnerabilities.csv` | 114 rows — open vulnerabilities |
| `threat_intelligence.csv` | 40 rows — active threat campaigns (25 match, 15 noise) |
| `business_services.csv` | 20 rows — business service catalog |
| `remediation_guidance.csv` | 30 rows — one-line hints (used only as a hint, not the answer) |
| `synthetic_threat_report.md` | 1-page MDR advisory |

`load_data.py` will fail loudly if any of these are missing.
