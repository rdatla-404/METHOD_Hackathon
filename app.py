"""Interconnection Intake Gatekeeper — data-driven pre-submission checks."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Interconnection Intake Gatekeeper", page_icon="⚡", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1,h2,h3 { font-family: 'Manrope', sans-serif; letter-spacing: -.03em; }
.stApp { background: #f5f7fa; }
.block-container { padding-top: 2rem; max-width: 1440px; }
[data-testid="stMetric"] { background: white; border: 1px solid #e7ebf0; border-radius: 12px; padding: 16px; }
.hero { background: linear-gradient(120deg,#10213a,#18395b); color:white; padding:28px 32px; border-radius:16px; margin-bottom:20px; }
.hero p { color:#c7d4e4; margin-bottom:0; }
</style>
""", unsafe_allow_html=True)


def read_table(file) -> pd.DataFrame:
    name = file.name.lower()
    data = file.getvalue()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data), dtype=object)
    if name.endswith((".csv", ".tsv", ".txt")):
        return pd.read_csv(io.BytesIO(data), sep="\t" if name.endswith((".tsv", ".txt")) else ",", dtype=object)
    raise ValueError("Upload a CSV or Excel file.")


def digest(file) -> str:
    return hashlib.sha256(file.getvalue()).hexdigest()


def norm(value: Any) -> str:
    return str(value).strip().casefold() if pd.notna(value) else ""


def compare_rule(rule: dict, submission: pd.DataFrame, refs: dict[str, pd.DataFrame]) -> list[dict]:
    field, kind = rule["field"], rule["kind"]
    if field not in submission.columns:
        return [{"Field": field, "Row": "—", "Verdict": "UNVERIFIABLE", "Finding": "Field is not present in the submission.", "Source": "—", "Source row": "—", "Fix": "Add this field to the submission or map the rule to the correct column."}]
    values = submission[field]
    result = []
    ref_name = rule.get("ref", "")
    ref_col = rule.get("ref_col", "")
    ref = refs.get(ref_name)
    if kind == "Required":
        for i, value in values.items():
            empty = norm(value) in ("", "nan", "none")
            result.append({"Field": field, "Row": int(i)+1, "Verdict": "FIX" if empty else "PASS", "Finding": "Required value is missing." if empty else "Value is present.", "Source": "Submission", "Source row": int(i)+1, "Fix": "Provide a value." if empty else "—"})
        return result
    if ref is None or ref_col not in ref.columns:
        return [{"Field": field, "Row": "—", "Verdict": "UNVERIFIABLE", "Finding": f"Reference column '{ref_col}' is unavailable in '{ref_name}'.", "Source": ref_name or "—", "Source row": "—", "Fix": "Upload the correct extract and map its reference column."}]
    if kind == "Allowed value (reference list)":
        index = {}
        for ridx, rvalue in ref[ref_col].items():
            key = norm(rvalue)
            if key:
                index.setdefault(key, []).append((int(ridx)+1, str(rvalue)))
        for i, value in values.items():
            key = norm(value)
            if not key:
                result.append({"Field": field, "Row": int(i)+1, "Verdict": "UNVERIFIABLE", "Finding": "No value supplied to compare against the reference list.", "Source": ref_name, "Source row": "—", "Fix": "Provide a value, then check again."})
            elif key in index:
                rows = index[key]
                result.append({"Field": field, "Row": int(i)+1, "Verdict": "PASS", "Finding": "Value found in reference extract.", "Source": ref_name, "Source row": ", ".join(str(x[0]) for x in rows[:5]), "Fix": "—"})
            else:
                result.append({"Field": field, "Row": int(i)+1, "Verdict": "FIX", "Finding": f"'{value}' was not found in the reference extract.", "Source": ref_name, "Source row": "—", "Fix": f"Choose a value listed in {ref_col}."})
        return result
    # Numeric upper-bound check using the actual maximum in an uploaded extract.
    ref_num = pd.to_numeric(ref[ref_col], errors="coerce").dropna()
    if ref_num.empty:
        return [{"Field": field, "Row": "—", "Verdict": "UNVERIFIABLE", "Finding": f"No numeric values found in '{ref_col}'.", "Source": ref_name, "Source row": "—", "Fix": "Select a numeric column from the extract."}]
    limit = float(ref_num.max())
    max_row = int(ref_num.idxmax()) + 1
    for i, value in values.items():
        number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        if pd.isna(number):
            verdict, finding, fix = "UNVERIFIABLE", "Value is missing or not numeric, so it cannot be compared.", "Enter a numeric value."
        elif float(number) > limit:
            verdict, finding, fix = "FIX", f"{number:g} exceeds the largest value ({limit:g}) in the extract.", f"Review the value; the extract maximum is {limit:g}."
        else:
            verdict, finding, fix = "PASS", f"{number:g} is within the observed extract maximum ({limit:g}).", "—"
        result.append({"Field": field, "Row": int(i)+1, "Verdict": verdict, "Finding": finding, "Source": ref_name, "Source row": max_row, "Fix": fix})
    return result


st.markdown('<div class="hero"><div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#f0a28e;font-weight:700">NE-RTO · Intake quality</div><h1 style="margin:.35rem 0">Interconnection Intake Gatekeeper</h1><p>Check a draft against current system extracts. Get field-level fixes before the review queue.</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("1 · Reference extracts")
    st.caption("Upload current NE-RTO source data. Reference values are never built into the checker.")
    extract_files = st.file_uploader("Add one or more extracts", type=["csv", "tsv", "txt", "xlsx", "xls"], accept_multiple_files=True, key="extracts")
    extracts: dict[str, pd.DataFrame] = {}
    extract_hashes = {}
    for f in extract_files or []:
        try:
            extracts[f.name] = read_table(f)
            extract_hashes[f.name] = digest(f)
            st.success(f"{f.name} · {len(extracts[f.name]):,} rows")
        except Exception as exc:
            st.error(f"{f.name}: {exc}")
    st.divider()
    st.header("2 · Draft submission")
    submission_file = st.file_uploader("Upload submission (CSV or Excel)", type=["csv", "tsv", "xlsx", "xls"], key="submission")

if extracts:
    with st.expander("Inspect uploaded source data", expanded=False):
        for name, df in extracts.items():
            st.markdown(f"**{name}** · {len(df):,} rows × {len(df.columns)} columns")
            st.dataframe(df.head(8), use_container_width=True, hide_index=True)

submission = None
if submission_file:
    try:
        submission = read_table(submission_file)
        if submission.empty:
            st.error("The submission file has no rows.")
            submission = None
    except Exception as exc:
        st.error(f"Could not read submission: {exc}")

if submission is not None:
    st.subheader("3 · Map checks to real extract columns")
    st.caption("Start with required fields, then choose reference-backed checks. Reference-list checks are exact after trimming and case-folding. Numeric checks use the extract's observed maximum; confirm that limit is meaningful before relying on it.")
    fields = list(submission.columns)
    rule_count = st.number_input("Number of checks", min_value=1, max_value=20, value=min(4, max(1, len(fields))), step=1)
    rules = []
    ref_names = list(extracts)
    for ix in range(int(rule_count)):
        with st.container(border=True):
            cols = st.columns([1.2, 1.3, 1.6, 1.6])
            field = cols[0].selectbox(f"Submission field · {ix+1}", fields, key=f"f{ix}")
            kind = cols[1].selectbox("Rule", ["Required", "Allowed value (reference list)", "Numeric ≤ extract maximum"], key=f"k{ix}")
            rule = {"field": field, "kind": kind}
            if kind != "Required":
                ref_name = cols[2].selectbox("Reference extract", ref_names, key=f"r{ix}")
                ref_cols = list(extracts[ref_name].columns)
                ref_col = cols[3].selectbox("Reference column", ref_cols, key=f"c{ix}")
                rule.update(ref=ref_name, ref_col=ref_col)
                if kind == "Numeric ≤ extract maximum":
                    numeric_count = pd.to_numeric(extracts[ref_name][ref_col], errors="coerce").notna().sum()
                    if not numeric_count:
                        st.warning(f"{ref_col} contains no numeric values. This rule will be UNVERIFIABLE.")
                    else:
                        st.caption(f"Observed maximum from uploaded data: {pd.to_numeric(extracts[ref_name][ref_col], errors='coerce').max():g}")
            rules.append(rule)
    if st.button("Run pre-check", type="primary", use_container_width=True):
        findings = []
        for rule in rules:
            findings.extend(compare_rule(rule, submission, extracts))
        report = pd.DataFrame(findings)
        st.session_state["last_findings"] = findings
        st.session_state["last_report_meta"] = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "submission": submission_file.name, "submission_sha256": digest(submission_file), "extract_hashes": extract_hashes, "rules": rules}

if "last_findings" in st.session_state:
    findings = st.session_state["last_findings"]
    report = pd.DataFrame(findings)
    meta = st.session_state["last_report_meta"]
    current_submission_hash = digest(submission_file) if submission_file else None
    current_extract_hashes = extract_hashes
    if current_submission_hash != meta["submission_sha256"] or current_extract_hashes != meta["extract_hashes"]:
        st.warning("Uploaded file(s) changed after this report was generated. Run the pre-check again before sharing it.")
    counts = report["Verdict"].value_counts()
    nfix, nunver = int(counts.get("FIX", 0)), int(counts.get("UNVERIFIABLE", 0))
    verdict = "FIX" if nfix else ("UNVERIFIABLE" if nunver else "PASS")
    st.subheader("Pre-check result")
    message = {"PASS": "All configured checks passed. This report covers only the rules shown below.", "FIX": "Some fields need attention. Fix them and run the check again.", "UNVERIFIABLE": "Some values could not be checked. Review them before submitting."}[verdict]
    if verdict == "PASS": st.success(f"PASS · {message}")
    elif verdict == "FIX": st.error(f"FIX · {message}")
    else: st.warning(f"UNVERIFIABLE · {message}")
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Pass", int(counts.get("PASS",0)))
    m2.metric("Fix", nfix)
    m3.metric("Unverifiable", nunver)
    m4.metric("Submission rows", len(submission) if submission is not None else "—")
    st.dataframe(report, use_container_width=True, hide_index=True)
    payload = {**meta, "overall_verdict": verdict, "counts": {str(k): int(v) for k,v in counts.items()}, "findings": findings}
    left,right = st.columns(2)
    left.download_button("Download shareable JSON report", json.dumps(payload, indent=2, ensure_ascii=False), file_name="intake-precheck-report.json", mime="application/json", use_container_width=True)
    right.download_button("Download findings CSV", report.to_csv(index=False), file_name="intake-precheck-findings.csv", mime="text/csv", use_container_width=True)
    st.caption(f"Checked {meta['checked_at']} · Submission: {meta['submission']} · SHA-256: {meta['submission_sha256'][:16]}…")
    with st.expander("Extract versions and configured checks"):
        st.json({"extract_sha256": meta["extract_hashes"], "rules": meta["rules"]})

if st.session_state.get("last_findings"):
    findings = st.session_state["last_findings"]
    bad = pd.DataFrame(findings)
    bad = bad[bad["Verdict"] != "PASS"]
    if not bad.empty:
        st.subheader("Intake team · recurring reasons")
        tally = bad.groupby(["Field", "Verdict", "Finding"], dropna=False).size().reset_index(name="Occurrences").sort_values("Occurrences", ascending=False)
        st.dataframe(tally, use_container_width=True, hide_index=True)
else:
    st.info("Upload the reference extracts and a draft submission in the left panel to begin. No demonstration data is used.")

st.divider()
st.caption("A PASS means only that the configured checks matched the uploaded data at the time shown. It is a pre-check, not an intake acceptance or technical study decision.")
