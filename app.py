"""Interconnection Intake Gatekeeper — data-driven pre-submission checks."""
"""Interconnection Intake Gatekeeper: evidence-based checks and queue visibility."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


st.set_page_config(page_title="Interconnection Intake Gatekeeper", page_icon="⚡", layout="wide")
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "gatekeeper_data.sqlite3"
RULE_TYPES = ["Required", "Allowed value (reference list)", "Numeric ≤ approved limit"]
STATUSES = ["Submitted", "In review", "Waiting on applicant", "Ready for handoff", "Closed"]

st.set_page_config(page_title="Interconnection Intake Gatekeeper", page_icon="⚡", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
@@ -28,182 +34,313 @@
""", unsafe_allow_html=True)


def connect_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS rule_sets (name TEXT PRIMARY KEY, rules_json TEXT NOT NULL, updated_at TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS check_history (id INTEGER PRIMARY KEY AUTOINCREMENT, checked_at TEXT NOT NULL, submission_name TEXT NOT NULL, submission_sha256 TEXT NOT NULL, verdict TEXT NOT NULL, counts_json TEXT NOT NULL, findings_json TEXT NOT NULL, metadata_json TEXT NOT NULL)")
    db.commit()
    return db


def read_table(file) -> pd.DataFrame:
    name = file.name.lower()
    data = file.getvalue()
    name, data = file.name.lower(), file.getvalue()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data), dtype=object)
    if name.endswith((".csv", ".tsv", ".txt")):
        return pd.read_csv(io.BytesIO(data), sep="\t" if name.endswith((".tsv", ".txt")) else ",", dtype=object)
    raise ValueError("Upload a CSV or Excel file.")


def digest(file) -> str:
    return hashlib.sha256(file.getvalue()).hexdigest()
def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(file) -> str:
    return sha(file.getvalue())


def norm(value: Any) -> str:
    return str(value).strip().casefold() if pd.notna(value) else ""


def compare_rule(rule: dict, submission: pd.DataFrame, refs: dict[str, pd.DataFrame]) -> list[dict]:
    field, kind = rule["field"], rule["kind"]
def display_date(value: Any) -> str:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return "Not supplied"
    return str(value)


def run_rule(rule: dict, submission: pd.DataFrame, refs: dict[str, pd.DataFrame]) -> list[dict]:
    field, kind = rule.get("field", ""), rule.get("kind", "")
    base = {"Field": field, "Source": "—", "Source row": "—"}
    if field not in submission.columns:
        return [{"Field": field, "Row": "—", "Verdict": "UNVERIFIABLE", "Finding": "Field is not present in the submission.", "Source": "—", "Source row": "—", "Fix": "Add this field to the submission or map the rule to the correct column."}]
    values = submission[field]
    result = []
    ref_name = rule.get("ref", "")
    ref_col = rule.get("ref_col", "")
    ref = refs.get(ref_name)
        return [{**base, "Row": "—", "Verdict": "UNVERIFIABLE", "Finding": "Mapped field is not present in the submission.", "Fix": "Check the field mapping or add the field to the submission."}]
    findings = []
    if kind == "Required":
        for i, value in values.items():
            empty = norm(value) in ("", "nan", "none")
            result.append({"Field": field, "Row": int(i)+1, "Verdict": "FIX" if empty else "PASS", "Finding": "Required value is missing." if empty else "Value is present.", "Source": "Submission", "Source row": int(i)+1, "Fix": "Provide a value." if empty else "—"})
        return result
    if ref is None or ref_col not in ref.columns:
        return [{"Field": field, "Row": "—", "Verdict": "UNVERIFIABLE", "Finding": f"Reference column '{ref_col}' is unavailable in '{ref_name}'.", "Source": ref_name or "—", "Source row": "—", "Fix": "Upload the correct extract and map its reference column."}]
        for idx, value in submission[field].items():
            missing = norm(value) in ("", "nan", "none")
            findings.append({**base, "Row": int(idx)+1, "Verdict": "FIX" if missing else "PASS", "Finding": "Required value is missing." if missing else "Required value is present.", "Source": "Submission", "Source row": int(idx)+1, "Fix": "Provide a value." if missing else "—"})
        return findings

    ref_name, ref_col = rule.get("ref", ""), rule.get("ref_col", "")
    ref = refs.get(ref_name)
    if kind == "Allowed value (reference list)":
        index = {}
        if ref is None or ref_col not in ref.columns:
            return [{**base, "Row": "—", "Verdict": "UNVERIFIABLE", "Finding": "The configured reference extract or column is unavailable.", "Source": ref_name or "—", "Fix": "Upload the extract version used to configure this rule."}]
        values = {}
        for ridx, rvalue in ref[ref_col].items():
            key = norm(rvalue)
            if key:
                index.setdefault(key, []).append((int(ridx)+1, str(rvalue)))
        for i, value in values.items():
                values.setdefault(key, []).append(int(ridx)+1)
        complete = bool(rule.get("complete_list", False))
        for idx, value in submission[field].items():
            key = norm(value)
            if not key:
                result.append({"Field": field, "Row": int(i)+1, "Verdict": "UNVERIFIABLE", "Finding": "No value supplied to compare against the reference list.", "Source": ref_name, "Source row": "—", "Fix": "Provide a value, then check again."})
            elif key in index:
                rows = index[key]
                result.append({"Field": field, "Row": int(i)+1, "Verdict": "PASS", "Finding": "Value found in reference extract.", "Source": ref_name, "Source row": ", ".join(str(x[0]) for x in rows[:5]), "Fix": "—"})
                verdict, finding, fix, srcrow = "UNVERIFIABLE", "No value was supplied to compare.", "Provide a value and check again.", "—"
            elif key in values:
                verdict, finding, fix, srcrow = "PASS", "Value found in the uploaded reference extract.", "—", ", ".join(map(str, values[key][:5]))
            elif complete:
                verdict, finding, fix, srcrow = "FIX", f"Value is not listed in the reference column '{ref_col}'.", f"Confirm the value or ask the data owner to verify the reference list.", "—"
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
                verdict, finding, fix, srcrow = "UNVERIFIABLE", "Value was not found, but this extract is not declared complete; absence is not proof of an error.", "Confirm with the data owner or use a complete authoritative list.", "—"
            findings.append({**base, "Row": int(idx)+1, "Verdict": verdict, "Finding": finding, "Source": ref_name, "Source row": srcrow, "Fix": fix})
        return findings

    if kind == "Numeric ≤ approved limit":
        limit, evidence = rule.get("limit"), str(rule.get("approval", "")).strip()
        try:
            limit = float(limit)
        except (TypeError, ValueError):
            limit = None
        if limit is None or not evidence:
            return [{**base, "Row": "—", "Verdict": "UNVERIFIABLE", "Finding": "This numeric limit has no valid threshold and approval reference.", "Source": evidence or "—", "Fix": "Enter an explicit approved threshold and its policy/source reference."}]
        for idx, value in submission[field].items():
            number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
            if pd.isna(number):
                verdict, finding, fix = "UNVERIFIABLE", "Value is missing or not numeric.", "Enter a numeric value."
            elif float(number) <= limit:
                verdict, finding, fix = "PASS", f"{number:g} is within the approved limit ({limit:g}).", "—"
            else:
                verdict, finding, fix = "FIX", f"{number:g} exceeds the approved limit ({limit:g}).", f"Review the value against policy {evidence}."
            findings.append({**base, "Row": int(idx)+1, "Verdict": verdict, "Finding": finding, "Source": f"Approved policy: {evidence}", "Source row": "—", "Fix": fix})
        return findings
    return [{**base, "Row": "—", "Verdict": "UNVERIFIABLE", "Finding": "Unknown rule type.", "Fix": "Review the saved rule set."}]


def overall_verdict(findings: list[dict]) -> str:
    verdicts = {item["Verdict"] for item in findings}
    if "FIX" in verdicts:
        return "FIX"
    if "UNVERIFIABLE" in verdicts or not verdicts:
        return "UNVERIFIABLE"
    return "PASS"


st.markdown('<div class="hero"><div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#f0a28e;font-weight:700">NE-RTO · Intake quality</div><h1 style="margin:.35rem 0">Interconnection Intake Gatekeeper</h1><p>Check a draft against current system extracts. Get field-level fixes before the review queue.</p></div>', unsafe_allow_html=True)
def save_history(meta: dict, findings: list[dict], verdict: str) -> None:
    counts = pd.Series([x["Verdict"] for x in findings]).value_counts().to_dict()
    with connect_db() as db:
        db.execute("INSERT INTO check_history (checked_at, submission_name, submission_sha256, verdict, counts_json, findings_json, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)", (meta["checked_at"], meta["submission"], meta["submission_sha256"], verdict, json.dumps(counts), json.dumps(findings, ensure_ascii=False), json.dumps(meta, ensure_ascii=False)))


def history_rows() -> pd.DataFrame:
    with connect_db() as db:
        return pd.read_sql_query("SELECT id, checked_at, submission_name, verdict, counts_json, findings_json, metadata_json FROM check_history ORDER BY id DESC", db)


st.markdown('<div class="hero"><div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#f0a28e;font-weight:700">NE-RTO · Intake quality & flow</div><h1 style="margin:.35rem 0">Interconnection Intake Gatekeeper</h1><p>Resolve preventable issues early, keep work visible, and give applicants a clearer next step.</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("1 · Reference extracts")
    st.caption("Upload current NE-RTO source data. Reference values are never built into the checker.")
    extract_files = st.file_uploader("Add one or more extracts", type=["csv", "tsv", "txt", "xlsx", "xls"], accept_multiple_files=True, key="extracts")
    st.header("Reference extracts")
    st.caption("Upload current source data. Reference values are loaded from these files at runtime.")
    extract_files = st.file_uploader("Add extracts", type=["csv", "tsv", "txt", "xlsx", "xls"], accept_multiple_files=True, key="extracts")
    extracts: dict[str, pd.DataFrame] = {}
    extract_hashes = {}
    extract_hashes: dict[str, str] = {}
    for f in extract_files or []:
        try:
            extracts[f.name] = read_table(f)
            extract_hashes[f.name] = digest(f)
            extract_hashes[f.name] = file_sha(f)
            st.success(f"{f.name} · {len(extracts[f.name]):,} rows")
        except Exception as exc:
            st.error(f"{f.name}: {exc}")
    with st.expander("Record source dates"):
        extract_dates = {}
        for name in extracts:
            extract_dates[name] = st.text_input(f"Source date · {name}", placeholder="Enter date printed in extract", key=f"date-{name}")
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
    st.header("Draft submission")
    submission_file = st.file_uploader("Upload draft (CSV or Excel)", type=["csv", "tsv", "xlsx", "xls"], key="submission")

tabs = st.tabs(["Pre-check", "Backlog & planning", "History & patterns"])

with tabs[0]:
    if extracts:
        with st.expander("Inspect real source data", expanded=False):
            for name, df in extracts.items():
                st.markdown(f"**{name}** · {len(df):,} rows × {len(df.columns)} columns · source date: {display_date(extract_dates.get(name))}")
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
        st.subheader("Configure defensible checks")
        st.caption("Missing values only become FIX when the reference is explicitly marked complete. Numeric limits require a documented approved threshold; the app never infers a business limit from an extract maximum.")
        with connect_db() as db:
            saved = db.execute("SELECT name, rules_json, updated_at FROM rule_sets ORDER BY name").fetchall()
        saved_map = {row[0]: json.loads(row[1]) for row in saved}
        saved_names = ["Start new rule set"] + list(saved_map)
        selected_saved = st.selectbox("Load saved rule set", saved_names)
        if selected_saved != "Start new rule set" and st.button("Load selected rules"):
            st.session_state["rule_draft"] = saved_map[selected_saved]
            st.rerun()
        rules = st.session_state.get("rule_draft")
        if not rules:
            rules = [{"field": str(submission.columns[0]), "kind": "Required"}]
        count = st.number_input("Number of checks", 1, 20, min(4, max(1, len(rules))), key="rule-count")
        rules = (rules + [{"field": str(submission.columns[0]), "kind": "Required"} for _ in range(max(0, int(count)-len(rules)))])[:int(count)]
        for ix in range(len(rules)):
            rule = rules[ix]
            st.markdown(f"**Check {ix+1}**")
            a,b,c,d = st.columns([1.3,1.5,1.6,1.7])
            field_options = list(map(str, submission.columns))
            field_index = field_options.index(rule["field"]) if rule.get("field") in field_options else 0
            rule["field"] = a.selectbox("Submission field", field_options, index=field_index, key=f"field-{ix}")
            kind_index = RULE_TYPES.index(rule["kind"]) if rule.get("kind") in RULE_TYPES else 0
            rule["kind"] = b.selectbox("Rule type", RULE_TYPES, index=kind_index, key=f"kind-{ix}")
            if rule["kind"] == "Allowed value (reference list)" and extracts:
                ref_names = list(extracts)
                ref_index = ref_names.index(rule["ref"]) if rule.get("ref") in ref_names else 0
                rule["ref"] = c.selectbox("Reference extract", ref_names, index=ref_index, key=f"ref-{ix}")
                ref_cols = list(map(str, extracts[rule["ref"]].columns))
                col_index = ref_cols.index(rule["ref_col"]) if rule.get("ref_col") in ref_cols else 0
                rule["ref_col"] = d.selectbox("Reference column", ref_cols, index=col_index, key=f"refcol-{ix}")
                rule["complete_list"] = st.checkbox("This reference list is complete and authoritative", value=bool(rule.get("complete_list", False)), key=f"complete-{ix}", help="Leave unchecked unless the data owner confirms omissions mean the submitted value is invalid.")
            elif rule["kind"] == "Numeric ≤ approved limit":
                c1,c2 = st.columns(2)
                rule["limit"] = c1.number_input("Approved limit", value=float(rule.get("limit", 0)), key=f"limit-{ix}")
                rule["approval"] = c2.text_input("Policy / approval reference", value=str(rule.get("approval", "")), key=f"approval-{ix}")
        st.session_state["rule_draft"] = rules
        name_col,save_col = st.columns([2,1])
        rule_name = name_col.text_input("Rule set name", value=selected_saved if selected_saved != "Start new rule set" else "", placeholder="e.g. Generator intake checks")
        if save_col.button("Save rule set", use_container_width=True):
            if not rule_name.strip():
                st.error("Enter a name before saving the rule set.")
            else:
                with connect_db() as db:
                    db.execute("INSERT INTO rule_sets(name,rules_json,updated_at) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET rules_json=excluded.rules_json, updated_at=excluded.updated_at", (rule_name.strip(), json.dumps(rules), datetime.now(timezone.utc).isoformat(timespec="seconds")))
                st.success(f"Saved '{rule_name.strip()}'.")
        if not extracts:
            st.warning("Upload at least one real extract to run a reference-backed check.")
        elif st.button("Run pre-check", type="primary", use_container_width=True):
            findings = [item for rule in rules for item in run_rule(rule, submission, extracts)]
            verdict = overall_verdict(findings)
            meta = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "submission": submission_file.name, "submission_sha256": file_sha(submission_file), "extract_hashes": extract_hashes, "extract_source_dates": extract_dates, "rules": rules, "rule_set": rule_name.strip() or None}
            save_history(meta, findings, verdict)
            st.session_state["last_findings"] = findings
            st.session_state["last_report_meta"] = meta
            st.session_state["last_verdict"] = verdict
            st.rerun()

    if st.session_state.get("last_findings"):
        findings = st.session_state["last_findings"]
        meta = st.session_state["last_report_meta"]
        counts = pd.Series([x["Verdict"] for x in findings]).value_counts().to_dict()
        verdict = st.session_state["last_verdict"]
        if submission_file is None or file_sha(submission_file) != meta["submission_sha256"] or extract_hashes != meta["extract_hashes"]:
            st.warning("An uploaded file changed since this check. Run it again before sharing the report.")
        st.subheader("Pre-check result")
        msg = {"PASS":"Configured checks passed against the uploaded versions.","FIX":"Resolve the listed issues and check again.","UNVERIFIABLE":"Some results need human confirmation; the tool did not guess."}[verdict]
        if verdict == "PASS": st.success(f"PASS · {msg}")
        elif verdict == "FIX": st.error(f"FIX · {msg}")
        else: st.warning(f"UNVERIFIABLE · {msg}")
        m1,m2,m3 = st.columns(3)
        m1.metric("Pass", int(counts.get("PASS",0)))
        m2.metric("Fix", int(counts.get("FIX",0)))
        m3.metric("Unverifiable", int(counts.get("UNVERIFIABLE",0)))
        result = pd.DataFrame(findings)
        st.dataframe(result, use_container_width=True, hide_index=True)
        public_report = {**meta, "overall_verdict": verdict, "counts": counts, "findings": findings, "applicant_next_step": "Correct FIX findings, confirm UNVERIFIABLE items with intake, then submit this report with the request."}
        left,right = st.columns(2)
        left.download_button("Download report for applicant", json.dumps(public_report, indent=2, ensure_ascii=False), file_name="intake-precheck-report.json", mime="application/json", use_container_width=True)
        right.download_button("Download findings CSV", result.to_csv(index=False), file_name="intake-precheck-findings.csv", mime="text/csv", use_container_width=True)
        st.info("Suggested applicant message: Fix items marked FIX. Items marked UNVERIFIABLE need intake confirmation. Attach this timestamped report when submitting. A pre-check is not formal acceptance.")
        st.caption(f"Checked {meta['checked_at']} UTC · Rule set: {meta.get('rule_set') or 'unsaved'} · Extract dates: {meta['extract_source_dates']}")
    else:
        st.info("Upload extracts and a draft, configure checks, and run the pre-check. No sample values are built into the app.")

with tabs[1]:
    st.subheader("Queue visibility & work planning")
    st.caption("Upload a real intake queue export. The app will calculate age and order open requests by age; it does not create calendar events or invent service targets.")
    queue_file = st.file_uploader("Upload intake queue (CSV or Excel)", type=["csv","tsv","xlsx","xls"], key="queue")
    if queue_file:
        try:
            queue = read_table(queue_file)
            if queue.empty:
                st.warning("The queue file has no rows.")
            else:
                qcols = list(map(str, queue.columns))
                x1,x2,x3,x4 = st.columns(4)
                id_col = x1.selectbox("Request ID column", qcols, key="qid")
                date_col = x2.selectbox("Received date column", qcols, key="qdate")
                status_col = x3.selectbox("Status column", ["(none)"]+qcols, key="qstatus")
                owner_col = x4.selectbox("Owner column", ["(none)"]+qcols, key="qowner")
                today = date.today()
                received = pd.to_datetime(queue[date_col], errors="coerce")
                queue_view = queue.copy()
                queue_view["Age (days)"] = (pd.Timestamp(today) - received.dt.normalize()).dt.days
                queue_view["Queue data issue"] = received.isna().map({True:"Received date missing or unreadable",False:""})
                open_mask = pd.Series(True, index=queue.index)
                if status_col != "(none)":
                    closed_words = {"closed","complete","completed","withdrawn","cancelled"}
                    open_mask = ~queue[status_col].map(norm).isin(closed_words)
                active = queue_view[open_mask].copy()
                active["Age (days)"] = pd.to_numeric(active["Age (days)"], errors="coerce")
                active = active.sort_values("Age (days)", ascending=False, na_position="last")
                n_open = len(active)
                median_age = active["Age (days)"].median() if n_open and active["Age (days)"].notna().any() else None
                oldest = active["Age (days)"].max() if n_open and active["Age (days)"].notna().any() else None
                k1,k2,k3 = st.columns(3)
                k1.metric("Open requests", n_open)
                k2.metric("Median age", f"{median_age:.0f} days" if pd.notna(median_age) else "Unavailable")
                k3.metric("Oldest request", f"{oldest:.0f} days" if pd.notna(oldest) else "Unavailable")
                stale_cutoff = st.number_input("Highlight requests at least this many days old (0 disables highlighting)", min_value=0, max_value=365, value=0)
                if stale_cutoff and "Age (days)" in active and (active["Age (days)"] >= stale_cutoff).any():
                    st.warning(f"{int((active['Age (days)'] >= stale_cutoff).sum())} open requests are at least {stale_cutoff} days old. Use this list to plan the next triage block.")
                view_cols = [id_col, date_col] + ([status_col] if status_col != "(none)" else []) + ([owner_col] if owner_col != "(none)" else []) + ["Age (days)","Queue data issue"]
                st.markdown("**Suggested work order:** oldest open requests first. Confirm urgency and dependencies with the intake team before assigning work.")
                st.dataframe(active[view_cols], use_container_width=True, hide_index=True)
                st.download_button("Download age-sorted worklist", active[view_cols].to_csv(index=False), file_name="intake-worklist.csv", mime="text/csv")
        except Exception as exc:
            st.error(f"Could not read queue: {exc}")
    else:
        st.info("Add a queue export with request ID and received date to see backlog size, age, and an age-sorted worklist. Status and owner fields are optional.")

with tabs[2]:
    st.subheader("Persistent check history & recurring issues")
    history = history_rows()
    if history.empty:
        st.info("Completed checks will appear here. History and saved rules are stored locally in gatekeeper_data.sqlite3 on this machine.")
    else:
        history_display = history[["id","checked_at","submission_name","verdict"]].rename(columns={"id":"Run","checked_at":"Checked at (UTC)","submission_name":"Submission","verdict":"Result"})
        st.dataframe(history_display, use_container_width=True, hide_index=True)
        aggregates = []
        for _, row in history.iterrows():
            for finding in json.loads(row["findings_json"]):
                if finding["Verdict"] != "PASS":
                    aggregates.append({"Field":finding["Field"],"Verdict":finding["Verdict"],"Finding":finding["Finding"],"Submission":row["submission_name"],"Checked at":row["checked_at"]})
        if aggregates:
            st.markdown("**Repeated non-passing reasons across saved runs**")
            agg = pd.DataFrame(aggregates)
            tally = agg.groupby(["Field","Verdict","Finding"],dropna=False).size().reset_index(name="Occurrences").sort_values("Occurrences",ascending=False)
            st.dataframe(tally, use_container_width=True, hide_index=True)
            st.download_button("Download recurring issue tally", tally.to_csv(index=False), file_name="recurring-intake-issues.csv", mime="text/csv")
        else:
            st.success("No non-passing findings recorded in saved runs.")

st.divider()
st.caption("A PASS means only that the configured checks matched the uploaded data at the time shown. It is a pre-check, not an intake acceptance or technical study decision.")
st.caption("A PASS applies only to the configured checks and uploaded file versions. This is a pre-check, not formal intake acceptance or a technical study decision. Queue data, rule sets, and history are local to this app folder; there is no account or API integration.")
