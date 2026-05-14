"""
TawasolPay Risk Assistant — Streamlit frontend.

Reads the FastAPI backend and renders the top-N risks as scannable cards
with NIST guidance, threat intel, and the LLM explanation.

Configure the backend URL via the sidebar, st.secrets["BACKEND_URL"], or
the TAWASOLPAY_BACKEND_URL environment variable. Default is localhost.
"""

import os
from datetime import datetime
from typing import Any

import requests
import streamlit as st

# ---------- Page config ----------
st.set_page_config(
    page_title="TawasolPay Risk Assistant",
    page_icon="🛡️",
    layout="wide",
)


# ---------- Config resolution ----------
def _default_backend() -> str:
    env = os.getenv("TAWASOLPAY_BACKEND_URL")
    if env:
        return env
    try:
        return st.secrets.get("BACKEND_URL", "http://localhost:8000")
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return "http://localhost:8000"
    except Exception:
        return "http://localhost:8000"


# ---------- API client ----------
# Cached inner functions: results are reused across reruns (slider tweaks,
# tab switches, widget interactions) until the user clicks "Refresh backend
# caches" in the sidebar — at which point we call st.cache_data.clear().
# Exceptions from the cached function propagate out and are NOT cached, so
# errors still render on transient failures.

@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_top_cached(backend: str, top_n: int) -> dict[str, Any]:
    r = requests.get(
        f"{backend.rstrip('/')}/risks/top",
        params={"top_n": top_n},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def fetch_top(backend: str, top_n: int) -> dict[str, Any] | None:
    try:
        return _fetch_top_cached(backend, top_n)
    except Exception as e:
        st.error(f"Could not load risks: {e}")
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_risk_cached(backend: str, risk_id: str) -> dict[str, Any] | None:
    r = requests.get(
        f"{backend.rstrip('/')}/risks/{risk_id}",
        timeout=120,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def fetch_risk(backend: str, risk_id: str) -> dict[str, Any] | None:
    try:
        return _fetch_risk_cached(backend, risk_id)
    except Exception as e:
        st.error(f"Lookup failed: {e}")
        return None


def trigger_refresh(backend: str) -> bool:
    # Generous timeout because the first request after an HF Space wake-up
    # has to cold-start the container + load the embedding model before it
    # can even reach the handler. Once warm, this call is sub-second.
    try:
        r = requests.post(f"{backend.rstrip('/')}/data/refresh", timeout=180)
        r.raise_for_status()
        return True
    except Exception as e:
        st.error(f"Refresh failed: {e}")
        return False


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_data_status_cached(backend: str) -> dict[str, Any]:
    # Same cold-start tolerance as the other endpoints — HF Spaces wake-up
    # can take ~60s before this lightweight handler even runs.
    r = requests.get(f"{backend.rstrip('/')}/data/status", timeout=180)
    r.raise_for_status()
    return r.json()


def fetch_data_status(backend: str) -> dict[str, Any] | None:
    try:
        return _fetch_data_status_cached(backend)
    except Exception as e:
        st.error(f"Status fetch failed: {e}")
        return None


# Datasets the backend's /data/upload/{dataset} accepts. The threat report
# goes through a separate endpoint, but we expose it here as a 6th choice for
# consistency.
UPLOAD_CHOICES = [
    "assets",
    "vulnerabilities",
    "threat_intelligence",
    "business_services",
    "remediation_guidance",
    "threat_report",
]


def upload_one(backend: str, dataset: str, filename: str, raw: bytes) -> dict[str, Any] | None:
    """Upload one CSV (or the threat report) to its endpoint. Returns the JSON or None."""
    if dataset == "threat_report":
        url = f"{backend.rstrip('/')}/data/upload/threat-report"
        mime = "text/markdown"
    else:
        url = f"{backend.rstrip('/')}/data/upload/{dataset}"
        mime = "text/csv"
    try:
        r = requests.post(
            url,
            files={"file": (filename, raw, mime)},
            timeout=120,
        )
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            st.error(f"{dataset}: {detail}")
            return None
        return r.json()
    except Exception as e:
        st.error(f"{dataset}: upload failed — {e}")
        return None


def clear_all_files(backend: str) -> dict[str, Any] | None:
    """Wipe every uploaded file from data/raw/ via POST /data/clear."""
    try:
        r = requests.post(f"{backend.rstrip('/')}/data/clear", timeout=180)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Clear failed: {e}")
        return None


def upload_batch(backend: str, files: dict[str, tuple[str, bytes]]) -> dict[str, Any] | None:
    """
    Upload all 5 CSVs (and optionally the threat report) in one call.

    `files` keys are: assets, vulnerabilities, threat_intelligence,
    business_services, remediation_guidance, threat_report (optional).
    """
    multipart: list[tuple[str, tuple[str, bytes, str]]] = []
    for key, (name, raw) in files.items():
        mime = "text/markdown" if key == "threat_report" else "text/csv"
        multipart.append((key, (name, raw, mime)))
    try:
        r = requests.post(
            f"{backend.rstrip('/')}/data/upload/batch",
            files=multipart,
            timeout=300,
        )
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            st.error(f"Batch upload failed: {detail}")
            return None
        return r.json()
    except Exception as e:
        st.error(f"Batch upload failed: {e}")
        return None


# ---------- Rendering ----------
def score_chip(score: float) -> str:
    if score >= 80:
        return "🔴"
    if score >= 60:
        return "🟠"
    return "🟡"


def render_risk_card(risk: dict[str, Any], expand_default: bool = False) -> None:
    rank = risk["rank"]
    score = risk["risk_score"]

    with st.container(border=True):
        cols = st.columns([1, 3, 3, 2])
        cols[0].markdown(f"### #{rank} {score_chip(score)}")
        cols[0].caption(f"Risk ID `{risk['risk_id']}`")
        cols[1].markdown(f"**{risk['cve_id']}**  \nCVSS {risk['cvss']}")
        cols[2].markdown(
            f"**{risk['asset_name']}**  \n`{risk['asset_id']}` · {risk['asset_environment']}"
        )
        cols[3].metric("Risk Score", f"{score:.1f}")

        badges: list[str] = []
        if risk.get("internet_exposed"):
            badges.append("🌐 internet-exposed")
        if risk.get("active_exploit"):
            badges.append("⚠️ active exploit")
        ti = risk.get("threat_intel")
        if ti and ti.get("ransomware_associated"):
            badges.append("💀 ransomware-linked")
        if badges:
            st.markdown(" &nbsp;·&nbsp; ".join(badges))

        st.caption(f"**Business service:** {risk.get('business_service', '—')}")

        if ti:
            actor = ti.get("actor", "Unknown")
            campaign = ti.get("campaign", "Unknown")
            st.markdown(
                f"**Threat intel match:** actor **{actor}** running campaign _{campaign}_"
            )

        with st.expander("Why this ranks here", expanded=expand_default):
            st.write(risk.get("explanation", "No explanation available."))

        controls = risk.get("nist_controls") or []
        with st.expander(f"NIST 800-53 guidance ({len(controls)} controls)"):
            if not controls:
                st.info("No NIST controls retrieved — vector store may be missing. Run `scripts/setup_data.py` or `POST /data/external/refresh/nist`.")
            for c in controls:
                st.markdown(f"**{c['control_id']} — {c['control_name']}** _(similarity {c['similarity_score']:.2f})_")
                excerpt = (c.get("excerpt") or "").strip()
                if len(excerpt) > 500:
                    excerpt = excerpt[:500].rstrip() + "…"
                st.caption(excerpt)
                st.markdown("---")


def render_generated_at(raw: str) -> str:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return raw or "unknown"


# ---------- Sidebar ----------
with st.sidebar:
    st.title("⚙️ Settings")
    backend = st.text_input(
        "Backend URL",
        value=_default_backend(),
        help="FastAPI service that exposes /risks/top",
    )
    top_n = st.slider("Top N risks", min_value=3, max_value=10, value=5)
    if st.button("🔄 Refresh backend caches", width="stretch"):
        if trigger_refresh(backend):
            st.cache_data.clear()
            st.success("Caches invalidated. Next request will reload from disk.")

    st.divider()
    st.subheader("🔍 Look up a single risk")
    risk_id_input = st.text_input(
        "Risk ID",
        placeholder="e.g. V-2019",
        help="The vuln_id from vulnerabilities.csv",
    )

    st.divider()
    st.caption("Built for the TawasolPay AI Engineer take-home. [NIST 800-53](https://csrc.nist.gov/projects/risk-management/sp800-53-controls)")

# ---------- Main ----------
st.title("🛡️ TawasolPay Risk Assistant")
st.caption("Top cyber risks ranked by a composite score across CVSS, internet exposure, active exploit availability, threat intel match, business criticality, and missing compensating controls. NIST 800-53 guidance is retrieved at request time via RAG — not hardcoded, not from the LLM's training data.")

tab_risks, tab_data = st.tabs(["📋 Top Risks", "📤 Data management"])

# ---------- Tab 1: Risks ----------
with tab_risks:
    if risk_id_input:
        st.subheader(f"Risk detail — `{risk_id_input}`")
        with st.spinner("Looking up risk…"):
            risk = fetch_risk(backend, risk_id_input.strip())
        if risk is None:
            st.warning(f"No risk found with ID '{risk_id_input}'.")
        else:
            render_risk_card(risk, expand_default=True)
    else:
        with st.spinner("Scoring risks and retrieving NIST guidance…"):
            data = fetch_top(backend, top_n)
        if data:
            st.caption(f"Generated at **{render_generated_at(data.get('generated_at', ''))}**")
            st.subheader(f"Top {len(data['risks'])} risks")
            for i, risk in enumerate(data["risks"]):
                render_risk_card(risk, expand_default=(i < 2))

# ---------- Tab 2: Data management ----------
with tab_data:
    st.subheader("Current data on disk")
    status = fetch_data_status(backend)
    if status:
        rows: list[dict[str, Any]] = []
        for ds in status.get("datasets", []):
            rows.append({
                "Dataset": ds["dataset"],
                "File": ds["filename"],
                "Present": "✅" if ds["present"] else "❌",
                "Rows": str(ds["rows"]) if ds["rows"] is not None else "—",
                "Size (KB)": round(ds["size_bytes"] / 1024, 1) if ds["size_bytes"] else 0,
                "Last modified": ds.get("last_modified") or "—",
            })
        tr = status.get("threat_report", {})
        rows.append({
            "Dataset": "threat_report",
            "File": tr.get("filename", "synthetic_threat_report.md"),
            "Present": "✅" if tr.get("present") else "❌",
            "Rows": "—",
            "Size (KB)": round((tr.get("size_bytes") or 0) / 1024, 1),
            "Last modified": tr.get("last_modified") or "—",
        })
        st.dataframe(rows, hide_index=True, width="stretch")

    st.divider()

    # --- Clear all uploaded files ---
    st.subheader("Clear uploaded files")
    st.caption(
        "Backs up each file to `data/backups/` then removes it from `data/raw/`. "
        "On Hugging Face Spaces, restarting the Space brings the committed files back."
    )
    confirm_clear = st.checkbox(
        "Yes, I want to delete all uploaded files",
        key="confirm_clear",
    )
    if st.button(
        "🗑️ Clear all uploaded files",
        type="secondary",
        disabled=not confirm_clear,
        width="stretch",
    ):
        with st.spinner("Clearing…"):
            result = clear_all_files(backend)
        if result:
            st.cache_data.clear()
            st.success(result.get("message", "Files cleared."))
            cleared = result.get("cleared") or []
            if cleared:
                st.markdown("**Cleared (backed up first)**")
                for c in cleared:
                    line = f"- `{c.get('dataset')}` — {c.get('filename')}"
                    if c.get("backup_created"):
                        line += f" → backup `{c['backup_created']}`"
                    st.markdown(line)
            absent = result.get("already_absent") or []
            if absent:
                st.caption(f"Already absent: {', '.join(absent)}")

    st.divider()

    # --- Single-file replace ---
    st.subheader("Replace a single file")
    st.caption("Pick a dataset, drop in a CSV (or the markdown for the threat report). The previous version is auto-backed-up to `data/backups/`.")
    col_a, col_b = st.columns([1, 2])
    dataset_pick = col_a.selectbox("Dataset", UPLOAD_CHOICES, index=0)
    accept_type = ["md", "markdown"] if dataset_pick == "threat_report" else ["csv"]
    single_file = col_b.file_uploader(
        f"Upload file for `{dataset_pick}`",
        type=accept_type,
        key=f"single_uploader_{dataset_pick}",
    )
    if st.button(
        "Replace file",
        type="primary",
        disabled=single_file is None,
        width="stretch",
    ):
        raw = single_file.getvalue()
        with st.spinner(f"Uploading {single_file.name}…"):
            result = upload_one(backend, dataset_pick, single_file.name, raw)
        if result:
            st.cache_data.clear()
            st.success(result.get("message", f"{dataset_pick} replaced."))
            res = result.get("result") or {}
            details = []
            if res.get("rows_written") is not None:
                details.append(f"{res['rows_written']} rows written")
            if res.get("backup_created"):
                details.append(f"backup → `{res['backup_created']}`")
            if details:
                st.caption(" · ".join(details))

    st.divider()

    # --- Batch replace ---
    st.subheader("Replace all files in one batch")
    st.caption("Drop in the 5 CSVs (and optionally the threat report). Files that fail validation are rejected individually — the rest still write.")
    batch_files: dict[str, tuple[str, bytes]] = {}
    bcols = st.columns(2)
    for i, ds in enumerate(UPLOAD_CHOICES[:5]):
        uploaded = bcols[i % 2].file_uploader(
            ds,
            type=["csv"],
            key=f"batch_uploader_{ds}",
        )
        if uploaded is not None:
            batch_files[ds] = (uploaded.name, uploaded.getvalue())
    tr_uploaded = st.file_uploader(
        "threat_report (optional)",
        type=["md", "markdown"],
        key="batch_uploader_threat_report",
    )
    if tr_uploaded is not None:
        batch_files["threat_report"] = (tr_uploaded.name, tr_uploaded.getvalue())

    if st.button(
        f"Upload batch ({len(batch_files)} file{'s' if len(batch_files) != 1 else ''})",
        type="primary",
        disabled=len(batch_files) == 0,
        width="stretch",
    ):
        with st.spinner("Uploading batch…"):
            result = upload_batch(backend, batch_files)
        if result:
            st.cache_data.clear()
            if result.get("success"):
                st.success(result.get("message", "Batch upload complete."))
            else:
                st.warning(result.get("message", "Batch upload had failures."))
            ok = result.get("results") or []
            if ok:
                st.markdown("**Written**")
                for r in ok:
                    line = f"- `{r.get('dataset')}` — {r.get('filename')}"
                    if r.get("rows_written") is not None:
                        line += f" ({r['rows_written']} rows)"
                    st.markdown(line)
            bad = result.get("failed") or []
            if bad:
                st.markdown("**Rejected**")
                for f in bad:
                    st.markdown(f"- `{f.get('dataset')}` — {f.get('error')}")
