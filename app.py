"""NE-RTO Interconnection Intake Gatekeeper, built around the supplied extracts."""

from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "gatekeeper_data.sqlite3"
REQUIRED_FIELDS = [
    "applicant_name", "project_name", "facility_type", "nameplate_capacity_mw",
    "poi_substation", "requested_voltage_kv", "gen_tie_required",
    "requested_inservice_date", "deposit_submitted",
]

st.set_page_config(page_title="NE-RTO Intake Gatekeeper", page_icon="⚡", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
html, body, [class*="css"] {font-family:'DM Sans',sans-serif}
h1,h2,h3 {font-family:'Manrope',sans-serif;letter-spacing:-.035em}
.stApp {background:#f4f6f8}.block-container {padding-top:1.5rem;max-width:1450px}
.hero {background:linear-gradient(115deg,#10213a,#174b66);color:#fff;padding:30px 34px;border-radius:18px;margin-bottom:20px}
.hero p {color:#cfdae4;margin:.4rem 0 0}.eyebrow {font-size:12px;letter-spacing:.15em;text-transform:uppercase;color:#f4a58f;font-weight:700}
[data-testid="stMetric"] {background:#fff;border:1px solid #e5e9ee;border-radius:12px;padding:14px}
</style>
""", unsafe_allow_html=True)


def connect_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS intake_check_history (id INTEGER PRIMARY KEY AUTOINCREMENT, checked_at TEXT NOT NULL, submission TEXT NOT NULL, verdict TEXT NOT NULL, findings TEXT NOT NULL, metadata TEXT NOT NULL)")
    db.commit()
    return db


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized(value: Any) -> str:
    return str(value).strip().casefold() if pd.notna(value) else ""


def normalize_submission_fields(frame: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "applicant_name": "applicant_name", "applicant": "applicant_name",
        "project_name": "project_name", "facility_type": "facility_type",
        "nameplate_capacity_mw": "nameplate_capacity_mw", "capacity_mw": "nameplate_capacity_mw",
        "poi_substation": "poi_substation", "point_of_interconnection": "poi_substation",
        "interconnection_substation": "poi_substation", "requested_voltage_kv": "requested_voltage_kv",
        "voltage_kv": "requested_voltage_kv", "gen_tie_required": "gen_tie_required",
        "generator_tie_required": "gen_tie_required", "gen_tie_length_miles": "gen_tie_length_miles",
        "generator_tie_length_miles": "gen_tie_length_miles", "requested_inservice_date": "requested_inservice_date",
        "requested_in_service_date": "requested_inservice_date", "requested_service_date": "requested_inservice_date", "deposit_submitted": "deposit_submitted",
        "deposit_amount": "deposit_amount",
    }
    renamed = {}
    for column in frame.columns:
        key = re.sub(r"[^a-z0-9]+", "_", str(column).strip().casefold()).strip("_")
        renamed[column] = aliases.get(key, key)
    out = frame.rename(columns=renamed).copy()
    if out.columns.duplicated().any():
        seen, unique = {}, []
        for column in out.columns:
            count = seen.get(column, 0)
            unique.append(column if count == 0 else f"{column}_{count+1}")
            seen[column] = count + 1
        out.columns = unique
    return out


def read_table_bytes(name: str, data: bytes) -> pd.DataFrame:
    suffix = Path(name).suffix.casefold()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(io.BytesIO(data), dtype=object)
    if suffix in {".csv", ".tsv", ".txt"}:
        return pd.read_csv(io.BytesIO(data), sep="\t" if suffix in {".tsv", ".txt"} else ",", dtype=object)
    if suffix == ".docx":
        return read_docx(data)
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        lines = [line for page in reader.pages for line in (page.extract_text() or "").splitlines()]
        return key_value_frame(lines, "PDF")
    raise ValueError("Supported submission formats: CSV, TSV, Excel (.xlsx/.xls), PDF, and Word (.docx). Save legacy .doc files as .docx first.")


def key_value_frame(lines: list[str], label: str) -> pd.DataFrame:
    pairs = {}
    clean = [str(line).strip() for line in lines if str(line).strip()]
    for line in clean:
        match = re.match(r"^\s*([^:=\t]{2,80}?)\s*[:=]\s*(.{1,500})\s*$", line)
        if match:
            pairs[match.group(1).strip()] = match.group(2).strip()
        elif "\t" in line:
            cells = [c.strip() for c in line.split("\t")]
            if len(cells) == 2 and all(cells):
                pairs[cells[0]] = cells[1]
    if pairs:
        return pd.DataFrame([pairs])
    text = "\n".join(clean)
    if not text:
        raise ValueError(f"No machine-readable text was found in this {label}. Scanned PDFs need OCR first.")
    return pd.DataFrame({"Document text (review required)": [text]})


def read_docx(data: bytes) -> pd.DataFrame:
    # DOCX is a ZIP package containing OOXML; parse it with the standard library
    # so the app does not fail to start when python-docx is absent in deployment.
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            root = ET.fromstring(package.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError("This .docx file is invalid or unreadable.") from exc
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    def cell_text(element) -> str:
        return "".join(node.text or "" for node in element.findall(".//w:t", ns)).strip()

    pairs = {}
    frames = []
    for table in root.findall(".//w:tbl", ns):
        rows = [[cell_text(cell) for cell in row.findall("./w:tc", ns)] for row in table.findall("./w:tr", ns)]
        rows = [row for row in rows if any(row)]
        if not rows:
            continue
        headers = rows[0]
        if len(headers) == 2 and headers[0].casefold() in {"field", "name", "item", "attribute"} and headers[1].casefold() in {"value", "answer", "response"}:
            for row in rows[1:]:
                if len(row) > 1 and row[0] and row[1]:
                    pairs[row[0]] = row[1]
        elif len(rows) == 1 and len(rows[0]) == 2:
            pairs[rows[0][0]] = rows[0][1]
        elif len(rows) > 1:
            width = len(headers)
            frames.append(pd.DataFrame([r[:width] + [""] * max(0, width-len(r)) for r in rows[1:]], columns=headers))
    paragraphs = [cell_text(p) for p in root.findall(".//w:p", ns)]
    for text in paragraphs:
        parsed = key_value_frame([text], "Word document") if text else None
        if parsed is not None and "Document text (review required)" not in parsed.columns:
            pairs.update(parsed.iloc[0].to_dict())
    if pairs:
        return pd.DataFrame([pairs])
    if frames:
        return frames[0]
    return key_value_frame(paragraphs, "Word document")


def validate_submission(frame: pd.DataFrame, refs: dict[str, pd.DataFrame], authoritative: dict[str, bool]) -> list[dict]:
    findings = []
    if "Document text (review required)" in frame.columns:
        return [{"Row": 1, "Field": "Document parsing", "Result": "UNVERIFIABLE", "Finding": "The file contains text, but named submission fields could not be safely extracted.", "Evidence": "Uploaded document", "Source row": "—", "Suggested action": "Use a labeled form/table (Field: Value) or upload CSV/Excel. Scanned PDFs require OCR."}]

    app_ref = refs.get("applicants", pd.DataFrame())
    sub_ref = refs.get("substations", pd.DataFrame())
    app_map = {}
    if {"applicant_name", "status"}.issubset(app_ref.columns):
        for idx, row in app_ref.iterrows():
            app_map.setdefault(normalized(row["applicant_name"]), []).append((int(idx)+1, str(row["status"]).strip()))
    sub_map = {}
    needed_sub = {"substation_name", "rated_voltage_kv", "available_hosting_capacity_mw"}
    if needed_sub.issubset(sub_ref.columns):
        for idx, row in sub_ref.iterrows():
            sub_map.setdefault(normalized(row["substation_name"]), []).append((int(idx)+1, row))

    for index, row in frame.iterrows():
        row_no = int(index)+1
        for field in REQUIRED_FIELDS:
            if field not in frame.columns:
                findings.append({"Row": row_no, "Field": field, "Result": "UNVERIFIABLE", "Finding": "Required field is absent from the submission file.", "Evidence": "Submission schema", "Source row": "—", "Suggested action": f"Add a '{field}' column and provide its value."})
            elif normalized(row[field]) in {"", "nan", "none"}:
                findings.append({"Row": row_no, "Field": field, "Result": "FIX", "Finding": "Required value is blank.", "Evidence": "Submission", "Source row": row_no, "Suggested action": f"Provide '{field}'."})
            else:
                findings.append({"Row": row_no, "Field": field, "Result": "PASS", "Finding": "Required value is present.", "Evidence": "Submission", "Source row": row_no, "Suggested action": "—"})

        # An applicant must be registered and active in the provided registration extract.
        applicant = normalized(row.get("applicant_name", ""))
        if applicant and not app_map:
            findings.append({"Row": row_no, "Field": "applicant_name", "Result": "UNVERIFIABLE", "Finding": "Registered-applicant extract is missing expected columns.", "Evidence": "registered_applicants extract", "Source row": "—", "Suggested action": "Load the extract with applicant_name and status columns."})
        elif applicant in app_map:
            matching = app_map[applicant]
            active = [(r, s) for r, s in matching if normalized(s) == "active"]
            if active:
                findings.append({"Row": row_no, "Field": "applicant_name", "Result": "PASS", "Finding": "Applicant is listed with Active status.", "Evidence": "registered_applicants extract", "Source row": ", ".join(str(r) for r, _ in active), "Suggested action": "—"})
            elif matching:
                findings.append({"Row": row_no, "Field": "applicant_name", "Result": "FIX", "Finding": f"Applicant is listed but status is '{matching[0][1]}'.", "Evidence": "registered_applicants extract", "Source row": str(matching[0][0]), "Suggested action": "Resolve the applicant's registration status with NE-RTO."})
        elif applicant:
            result = "FIX" if authoritative.get("applicants") else "UNVERIFIABLE"
            findings.append({"Row": row_no, "Field": "applicant_name", "Result": result, "Finding": "Applicant was not found in the provided registered-applicant extract.", "Evidence": "registered_applicants extract", "Source row": "—", "Suggested action": "Confirm registration; if the extract is not complete, ask the data owner to verify."})

        # POI existence, requested voltage, and capacity are linked to the same substation row.
        poi = normalized(row.get("poi_substation", ""))
        if poi and not sub_map:
            findings.append({"Row": row_no, "Field": "poi_substation", "Result": "UNVERIFIABLE", "Finding": "Substation extract is missing expected columns.", "Evidence": "substation reference extract", "Source row": "—", "Suggested action": "Load substation_name, rated_voltage_kv, and available_hosting_capacity_mw."})
        elif poi in sub_map:
            source_row, sub = sub_map[poi][0]
            findings.append({"Row": row_no, "Field": "poi_substation", "Result": "PASS", "Finding": "Point of interconnection matches a substation in the reference extract.", "Evidence": "substation reference extract", "Source row": source_row, "Suggested action": "—"})
            for field, ref_field, label in (("requested_voltage_kv", "rated_voltage_kv", "Voltage"), ("nameplate_capacity_mw", "available_hosting_capacity_mw", "Capacity")):
                if field not in frame.columns or pd.isna(row.get(field)):
                    continue
                submitted = pd.to_numeric(pd.Series([row[field]]), errors="coerce").iloc[0]
                reference = pd.to_numeric(pd.Series([sub[ref_field]]), errors="coerce").iloc[0]
                if pd.isna(submitted) or pd.isna(reference):
                    result, finding, action = "UNVERIFIABLE", f"{label} comparison requires numeric values in both files.", "Confirm the submitted and reference values."
                elif field == "requested_voltage_kv" and float(submitted) == float(reference):
                    result, finding, action = "PASS", f"Requested voltage matches substation rating ({reference:g} kV).", "—"
                elif field == "requested_voltage_kv":
                    result, finding, action = "FIX", f"Requested voltage ({submitted:g} kV) does not match substation rating ({reference:g} kV).", f"Review the requested voltage against the {sub_ref.iloc[source_row-1]['substation_name']} record."
                elif float(submitted) <= float(reference):
                    result, finding, action = "PASS", f"Nameplate capacity ({submitted:g} MW) is within substation hosting capacity ({reference:g} MW).", "—"
                else:
                    result, finding, action = "FIX", f"Nameplate capacity ({submitted:g} MW) exceeds substation hosting capacity ({reference:g} MW).", f"Review project capacity or select a POI with sufficient capacity. Reference capacity: {reference:g} MW."
                findings.append({"Row": row_no, "Field": field, "Result": result, "Finding": finding, "Evidence": "substation reference extract", "Source row": source_row, "Suggested action": action})
        elif poi:
            result = "FIX" if authoritative.get("substations") else "UNVERIFIABLE"
            findings.append({"Row": row_no, "Field": "poi_substation", "Result": result, "Finding": "Substation was not found in the provided reference extract.", "Evidence": "substation reference extract", "Source row": "—", "Suggested action": "Confirm the POI spelling or ask the data owner to verify the reference."})
    return findings


def verdict_for(findings: list[dict]) -> str:
    results = {f["Result"] for f in findings}
    return "FIX" if "FIX" in results else "UNVERIFIABLE" if "UNVERIFIABLE" in results or not findings else "PASS"


def history() -> pd.DataFrame:
    with connect_db() as db:
        return pd.read_sql_query("SELECT id, checked_at, submission, verdict, findings, metadata FROM intake_check_history ORDER BY id DESC", db)


refs: dict[str, pd.DataFrame] = {}
source_meta: dict[str, dict] = {}
with st.sidebar:
    st.markdown("### Reference data")
    st.caption("Choose the two NE-RTO reference files from your laptop. They are read for this app session and are not bundled with the website.")
    reference_files = st.file_uploader("Upload reference extracts", type=["xlsx", "xls", "csv"], accept_multiple_files=True, key="reference_files")
    for uploaded in reference_files or []:
        try:
            frame = read_table_bytes(uploaded.name, uploaded.getvalue())
            cols = set(map(str, frame.columns))
            if {"substation_name", "rated_voltage_kv", "available_hosting_capacity_mw"}.issubset(cols):
                refs["substations"] = frame
                source_meta["substations"] = {"name": uploaded.name, "sha256": digest(uploaded.getvalue()), "source": "User upload"}
            elif {"applicant_name", "status"}.issubset(cols):
                refs["applicants"] = frame
                source_meta["applicants"] = {"name": uploaded.name, "sha256": digest(uploaded.getvalue()), "source": "User upload"}
            else:
                st.error(f"{uploaded.name}: columns did not match a known NE-RTO extract.")
        except Exception as exc:
            st.error(f"Could not read {uploaded.name}: {exc}")
    st.divider()
    st.markdown("**Loaded sources**")
    for key, label in (("applicants", "Registered applicants"), ("substations", "Substations")):
        if key in refs:
            st.write(f"{label}: {len(refs[key]):,} records")
        else:
            st.error(f"{label} extract unavailable")

st.markdown('<div class="hero"><div class="eyebrow">NE-RTO · Generator interconnection intake</div><h1 style="margin:.35rem 0">A cleaner first submission</h1><p>Catch preventable intake issues before the review queue. See the evidence, fix the draft, and submit with a timestamped report.</p></div>', unsafe_allow_html=True)

stats = st.columns(4)
stats[0].metric("Requests rejected", "41%")
stats[1].metric("First review", "9 days")
stats[2].metric("Average resubmissions", "3.4")
stats[3].metric("Delay per incomplete file", "6 weeks")
st.caption("Client-brief baseline figures; the app does not claim these are measured outcomes from the uploaded extracts.")

tabs = st.tabs(["Check a draft", "Intake queue", "Team insights & rules"])

with tabs[0]:
    st.subheader("Check against the supplied NE-RTO records")
    st.write("The app looks up the applicant's registration status and validates the selected substation, voltage, and hosting capacity using the reference files uploaded from your laptop.")
    submission_name = ""
    submission_bytes = b""
    uploaded_submission = st.file_uploader("Upload a draft or the passing sample from your laptop", type=["csv", "tsv", "xlsx", "xls", "pdf", "docx"], key="draft")
    draft = None
    if uploaded_submission:
        submission_name = uploaded_submission.name
        submission_bytes = uploaded_submission.getvalue()
        try:
            draft = normalize_submission_fields(read_table_bytes(submission_name, submission_bytes))
        except Exception as exc:
            st.error(str(exc))
    authoritative = {}
    with st.expander("Reference list completeness", expanded=False):
        st.caption("An absent name in a partial extract is uncertain. Mark a list authoritative only if its data owner confirms it is complete for this intake check.")
        authoritative["applicants"] = st.checkbox("Registered-applicant extract is complete and authoritative", value=False, key="app-complete")
        authoritative["substations"] = st.checkbox("Substation reference extract is complete and authoritative", value=False, key="sub-complete")
    if draft is not None:
        if "Document text (review required)" in draft.columns:
            st.warning("This document did not expose named fields. Review its extracted text and use a labeled form or structured table for reliable checks.")
            with st.expander("Extracted text"):
                st.text(draft.iloc[0, 0])
        else:
            st.markdown("**Draft preview**")
            st.dataframe(draft, use_container_width=True, hide_index=True)
        if st.button("Run intake pre-check", type="primary", use_container_width=True, disabled=not refs):
            findings = validate_submission(draft, refs, authoritative)
            verdict = verdict_for(findings)
            checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            meta = {"checked_at": checked_at, "submission": submission_name, "submission_sha256": digest(submission_bytes), "reference_sources": source_meta, "authoritative_lists": authoritative}
            with connect_db() as db:
                db.execute("INSERT INTO intake_check_history (checked_at,submission,verdict,findings,metadata) VALUES(?,?,?,?,?)", (checked_at, submission_name, verdict, json.dumps(findings, ensure_ascii=False), json.dumps(meta, ensure_ascii=False)))
            st.session_state["latest_check"] = {"findings": findings, "verdict": verdict, "meta": meta}
            st.rerun()
    if st.session_state.get("latest_check"):
        latest = st.session_state["latest_check"]
        findings, verdict, meta = latest["findings"], latest["verdict"], latest["meta"]
        stale_report = not submission_bytes or digest(submission_bytes) != meta["submission_sha256"] or source_meta != meta["reference_sources"]
        if stale_report:
            st.warning("The submission or a reference extract changed after this report was generated. Run the check again before sharing it.")
        st.subheader("Pre-check result")
        if verdict == "PASS": st.success("PASS · All configured data-backed intake checks passed. Attach this report to the submission.")
        elif verdict == "FIX": st.error("FIX · Correct the findings below, then run the pre-check again.")
        else: st.warning("UNVERIFIABLE · The available source data cannot settle every finding. Ask intake to confirm those items.")
        results = pd.DataFrame(findings)
        counts = results["Result"].value_counts().to_dict()
        m1,m2,m3 = st.columns(3)
        m1.metric("Passed", int(counts.get("PASS",0)))
        m2.metric("Fix", int(counts.get("FIX",0)))
        m3.metric("Unverifiable", int(counts.get("UNVERIFIABLE",0)))
        st.dataframe(results, use_container_width=True, hide_index=True)
        report = {**meta, "overall_verdict": verdict, "findings": findings, "applicant_next_step": "Correct FIX items. Ask intake to confirm UNVERIFIABLE items. Attach this report when submitting."}
        c1,c2 = st.columns(2)
        c1.download_button("Download submission check report", json.dumps(report, indent=2, ensure_ascii=False), file_name="ne-rto-intake-check.json", mime="application/json", use_container_width=True, disabled=stale_report)
        c2.download_button("Download findings CSV", results.to_csv(index=False), file_name="ne-rto-intake-findings.csv", mime="text/csv", use_container_width=True, disabled=stale_report)
        st.caption(f"Report time (UTC): {meta['checked_at']} · Submission fingerprint: {meta['submission_sha256'][:20]}…")

with tabs[1]:
    st.subheader("Keep the intake queue visible")
    st.caption("Upload a real intake export to see request age and an oldest-first worklist. No service targets or records are assumed.")
    queue_file = st.file_uploader("Queue export (CSV or Excel)", type=["csv", "tsv", "xlsx", "xls"], key="queue")
    if queue_file:
        try:
            queue = read_table_bytes(queue_file.name, queue_file.getvalue())
            columns = list(map(str, queue.columns))
            a,b,c,d = st.columns(4)
            id_col = a.selectbox("Request ID", columns, key="queue-id")
            received_col = b.selectbox("Received date", columns, key="queue-date")
            status_col = c.selectbox("Status (optional)", ["(none)"]+columns, key="queue-status")
            owner_col = d.selectbox("Owner (optional)", ["(none)"]+columns, key="queue-owner")
            view = queue.copy()
            received = pd.to_datetime(view[received_col], errors="coerce")
            view["Age (days)"] = (pd.Timestamp(date.today())-received.dt.normalize()).dt.days
            open_mask = pd.Series(True,index=view.index)
            if status_col != "(none)":
                open_mask = ~view[status_col].map(normalized).isin({"closed","complete","completed","withdrawn","cancelled"})
            open_queue = view[open_mask].sort_values("Age (days)",ascending=False,na_position="last")
            k1,k2,k3 = st.columns(3)
            k1.metric("Open requests",len(open_queue))
            k2.metric("Median age",f"{open_queue['Age (days)'].median():.0f} days" if open_queue["Age (days)"].notna().any() else "Unknown")
            k3.metric("Oldest request",f"{open_queue['Age (days)'].max():.0f} days" if open_queue["Age (days)"].notna().any() else "Unknown")
            focus = st.number_input("Highlight age (days); 0 disables",min_value=0,max_value=365,value=0)
            if focus and (open_queue["Age (days)"]>=focus).any():
                st.warning(f"{int((open_queue['Age (days)']>=focus).sum())} open requests are at least {focus} days old. Consider them for the next team triage block.")
            shown = [id_col,received_col]+([status_col] if status_col!="(none)" else [])+([owner_col] if owner_col!="(none)" else [])+["Age (days)"]
            st.markdown("**Suggested work order:** oldest open items first. Confirm urgency, blockers, and ownership with the intake team.")
            st.dataframe(open_queue[shown],use_container_width=True,hide_index=True)
            st.download_button("Download age-sorted worklist",open_queue[shown].to_csv(index=False),file_name="intake-worklist.csv",mime="text/csv")
        except Exception as exc:
            st.error(f"Could not read queue: {exc}")
    else:
        st.info("Upload an actual queue export from your laptop to turn this view on; the app will not fabricate backlog data.")

with tabs[2]:
    st.subheader("Team insights, data lineage, and business rules")
    h = history()
    if h.empty:
        st.info("Completed checks will build a persistent local history here.")
    else:
        st.dataframe(h[["id","checked_at","submission","verdict"]].rename(columns={"id":"Run","checked_at":"Checked at (UTC)","submission":"Submission","verdict":"Result"}),use_container_width=True,hide_index=True)
        issues=[]
        for _, item in h.iterrows():
            for finding in json.loads(item["findings"]):
                if finding["Result"] != "PASS":
                    issues.append({"Field":finding["Field"],"Result":finding["Result"],"Finding":finding["Finding"]})
        if issues:
            tally=pd.DataFrame(issues).groupby(["Field","Result","Finding"],dropna=False).size().reset_index(name="Occurrences").sort_values("Occurrences",ascending=False)
            st.markdown("**Most common findings across saved checks**")
            st.dataframe(tally,use_container_width=True,hide_index=True)
    st.markdown("#### Checks grounded in supplied extracts")
    st.markdown("1. Required intake fields are present.\n2. Applicant is present in the registered-applicant extract and has Active status.\n3. Point of interconnection exists in the substation reference table.\n4. Requested voltage equals the selected substation rating.\n5. Nameplate capacity does not exceed the selected substation's available hosting capacity.")
    st.caption("Missing applicant or substation values stay UNVERIFIABLE unless the intake team confirms the corresponding uploaded extract is complete and authoritative. The app does not infer rules or use the largest observed data value as a policy limit.")
    st.markdown("#### Loaded source versions")
    for key, meta in source_meta.items():
        st.write(f"**{key.title()}** · {meta['name']} · {meta['source']} · SHA-256 {meta['sha256'][:20]}… · {len(refs[key]):,} rows")

st.divider()
st.caption("This prototype speeds up intake completeness checks; it does not accept requests or perform downstream technical studies. Queue management uses only the queue file supplied by the team. No API, account, email, or calendar integration is part of the hackathon scope.")
