# TawasolPay Risk Assistant

AI-powered cyber risk prioritization for a fictional payments company. Ingests TawasolPay's daily security data, scores every vulnerability across six signals, retrieves grounded NIST 800-53 guidance via RAG, and renders the top-N findings as a scannable Streamlit UI.

## Live demo

| Surface | URL |
|---|---|
| Frontend (Streamlit) | https://itspsk-tawasolpay-frontend.hf.space |
| Backend (FastAPI)    | https://itspsk-tawasolpay-backend.hf.space |
| Backend docs (Swagger) | https://itspsk-tawasolpay-backend.hf.space/docs |

Open the frontend, click **Load top risks**, and the UI shows 5 ranked risks with risk-score chips, threat-intel matches, retrieved NIST controls, and an LLM-generated explanation per finding.

## Repo layout

```
.
├── backend/      FastAPI service — scoring, RAG, LLM, data uploads
│   ├── src/
│   ├── data/         raw CSVs + reference data + persisted Chroma index
│   ├── docs/
│   │   ├── ARCHITECTURE.md     module-by-module walkthrough
│   │   └── DEPLOYMENT.md       how the two HF Spaces are wired up
│   └── README.md     setup + endpoints + assignment write-up (Q1/Q2/Q3)
└── frontend/     Streamlit UI — talks to the backend over HTTP
    └── README.md     setup + configuration
```

## What this solves

The assignment's "three things":

1. **Prioritize risks** — composite scoring across six signals (CVSS, internet exposure, active exploit, threat-intel match, business criticality, missing controls). CVSS alone is intentionally not enough.
2. **Ground the output** — every top-N risk runs through a multi-query RAG pass over NIST SP 800-53 Rev. 5 and the LLM is required to cite the retrieved control IDs.
3. **Make it readable** — Streamlit UI with status badges, expandable evidence, and a one-paragraph "Why this ranks here" explanation per card.

The full assignment write-up — what was embedded vs queried, three specific failure modes, the one change I'd ship next — is in [`backend/README.md`](backend/README.md#assignment-write-up).

## Quick start

Each service has its own quick-start in its README:

- **Backend** — [`backend/README.md`](backend/README.md#quick-start-local) (FastAPI, port 8000 locally / 7860 on HF)
- **Frontend** — [`frontend/README.md`](frontend/README.md#quick-start-local) (Streamlit, port 8501)

The deployed Spaces work out of the box — only a `GROQ_API_KEY` is needed on the backend; the frontend just points at the backend URL.

## License

MIT — see [`LICENSE`](LICENSE).
