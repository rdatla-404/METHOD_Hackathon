"""Interconnection Intake Gatekeeper.
Applicants upload ONE draft submission; it is checked against NE-RTO reference data that
ships with the backend (data/). Nothing else is uploaded."""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from backend import run_precheck, load_reference, reference_fingerprint

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "gatekeeper_data.sqlite3"
ICON = {"PASS": "✅ Pass", "FLAG": "🚩 Accepted, flagged", "FAIL": "❌ Failed",
        "UNVERIFIABLE": "⚠️ Could not verify", "NOT CHECKED": "➖ Not checked"}
BANNER = {"READY": ("success", "READY TO SUBMIT · no constraint failed (see any flagged items below)."),
          "NEEDS FIXES": ("warning", "NEEDS REVIEW · no constraint failed, but some could not be verified."),
          "NOT READY": ("error", "REJECTED · fix the failed constraints below and upload again.")}

st.set_page_config(page_title="Interconnection Intake Gatekeeper", page_icon="⚡", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Manrope', sans-serif; letter-spacing: -.03em; }
.stApp { background: #f5f7fa; }
.block-container { padding-top: 2rem; max-width: 1200px; }
[data-testid="stMetric"] { background: white; border: 1px solid #e7ebf0; border-radius: 12px; padding: 16px; }
.hero { background: linear-gradient(120deg,#10213a,#18395b); color:white; padding:28px 32px; border-radius:16px; margin-bottom:20px; }
.hero p { color:#c7d4e4; margin-bottom:0; }
</style>
""", unsafe_allow_html=True)


def connect_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS check_history (id INTEGER PRIMARY KEY AUTOINCREMENT, checked_at TEXT NOT NULL, "
               "submission_name TEXT NOT NULL, submission_sha256 TEXT NOT NULL, verdict TEXT NOT NULL, "
               "findings_json TEXT NOT NULL, metadata_json TEXT NOT NULL)")
    db.commit()
    return db


def read_submission(file) -> pd.DataFrame:
    name, data = file.name.lower(), file.getvalue()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data), dtype=object)
    if name.endswith((".csv", ".tsv", ".txt")):
        return pd.read_csv(io.BytesIO(data), sep="\t" if name.endswith((".tsv", ".txt")) else ",", dtype=object)
    raise ValueError("Upload a CSV or Excel file.")


def save_history(meta: dict, findings: list[dict], verdict: str) -> None:
    with connect_db() as db:
        db.execute("INSERT INTO check_history (checked_at, submission_name, submission_sha256, verdict, findings_json, metadata_json) "
                   "VALUES (?,?,?,?,?,?)", (meta["checked_at"], meta["submission"], meta["submission_sha256"], verdict,
                                            json.dumps(findings, ensure_ascii=False), json.dumps(meta, ensure_ascii=False)))


st.markdown('<div class="hero"><div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#f0a28e;font-weight:700">'
            'NE-RTO · Intake quality</div><h1 style="margin:.35rem 0">Interconnection Intake Gatekeeper</h1>'
            '<p>Upload your draft request and get an immediate, honest answer on which constraints it fails.</p></div>',
            unsafe_allow_html=True)

reference = load_reference()
if not reference:
    st.error("NE-RTO reference data is missing from the backend (data/ folder). Contact the administrator.")
    st.stop()

tab_check, tab_history = st.tabs(["Pre-check", "History & patterns"])

with tab_check:
    upload = st.file_uploader("Draft submission (CSV or Excel, one request per file)", type=["csv", "tsv", "xlsx", "xls"])
    if upload is None:
        st.info("Upload a draft submission to check it. Reference data is held by NE-RTO and applied automatically.")
    else:
        try:
            submission = read_submission(upload)
        except Exception as exc:
            st.error(f"Could not read the file: {exc}")
            st.stop()
        result = run_precheck(submission, reference)
        findings, constraints, verdict = result["findings"], result["constraints"], result["verdict"]
        digest = hashlib.sha256(upload.getvalue()).hexdigest()
        meta = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "submission": upload.name,
                "submission_sha256": digest, "reference_sha256": reference_fingerprint()}
        if st.session_state.get("saved_digest") != digest:   # log each distinct file once, not on every rerun
            save_history(meta, findings, verdict)
            st.session_state["saved_digest"] = digest

        kind, msg = BANNER[verdict]
        getattr(st, kind)(msg)
        n_fail = sum(c["status"] == "FAIL" for c in constraints)
        n_pass = sum(c["status"] in ("PASS", "FLAG") for c in constraints)
        n_skip = sum(c["status"] in ("NOT CHECKED", "UNVERIFIABLE") for c in constraints)
        m1, m2, m3 = st.columns(3)
        m1.metric("Passed", n_pass)
        m2.metric("Failed", n_fail)
        m3.metric("Not checked / unverifiable", n_skip)

        st.subheader("Constraints")
        table = pd.DataFrame([{"Constraint": c["constraint"], "Result": ICON[c["status"]]} for c in constraints])
        st.dataframe(table, use_container_width=True, hide_index=True)

        if findings:
            st.subheader("Findings")
            for f in findings:
                with st.container(border=True):
                    st.markdown(f"{'🚩' if f['Severity'] == 'info' else '❌'} **{f['Constraint']}**  \n`{f['Field']}` — {f['Finding']}")
                    st.markdown(f"**Fix:** {f['Fix']}")
                    st.caption(f"Rule source: {f['Source']}" + (f" · row {f['Source row']}" if f["Source row"] != "—" else ""))
            findings_df = pd.DataFrame(findings)
            c1, c2 = st.columns(2)
            c1.download_button("Download report (JSON)", json.dumps({**meta, "verdict": verdict, "constraints": constraints,
                               "findings": findings}, indent=2, ensure_ascii=False),
                               file_name="intake-precheck-report.json", mime="application/json", use_container_width=True)
            c2.download_button("Download findings (CSV)", findings_df.to_csv(index=False),
                               file_name="intake-precheck-findings.csv", mime="text/csv", use_container_width=True)
        st.caption(f"Checked {meta['checked_at']} UTC. A pre-check is not formal intake acceptance or a technical study decision.")

with tab_history:
    with connect_db() as db:
        history = pd.read_sql_query("SELECT id, checked_at, submission_name, verdict, findings_json FROM check_history ORDER BY id DESC", db)
    if history.empty:
        st.info("Completed checks will appear here (stored locally in gatekeeper_data.sqlite3).")
    else:
        st.dataframe(history[["id", "checked_at", "submission_name", "verdict"]].rename(
            columns={"id": "Run", "checked_at": "Checked at (UTC)", "submission_name": "Submission", "verdict": "Result"}),
            use_container_width=True, hide_index=True)
        rows = [{"Constraint": f["Constraint"], "Finding": f["Finding"]}
                for js in history["findings_json"] for f in json.loads(js)]
        if rows:
            st.markdown("**Most common reasons for rejection**")
            tally = (pd.DataFrame(rows).groupby("Constraint").size().reset_index(name="Occurrences")
                     .sort_values("Occurrences", ascending=False))
            st.dataframe(tally, use_container_width=True, hide_index=True)
            st.download_button("Download tally", tally.to_csv(index=False), file_name="recurring-intake-issues.csv", mime="text/csv")