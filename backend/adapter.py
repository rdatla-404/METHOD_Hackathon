"""Converts backend results into the row format app.py already uses."""
import pandas as pd
from .engine import validate


def run_backend_checks(submission: pd.DataFrame, extracts: dict) -> list[dict]:
    findings = []
    for idx, row in submission.iterrows():
        result = validate(row.to_dict(), ref=extracts)
        base = {"Row": int(idx) + 1}
        for i in result["issues"]:
            fix = i["fix"]
            if i["suggestions"]:
                fix += " Closest valid: " + ", ".join(map(str, i["suggestions"])) + "."
            findings.append({**base, "Field": i["field"], "Source": i["source"],
                             "Source row": i["source_row"],
                             # blockers are certain errors; warnings need a human
                             "Verdict": "FIX" if i["severity"] == "blocker" else "UNVERIFIABLE",
                             "Finding": i["message"], "Fix": fix})
        if not result["issues"]:
            findings.append({**base, "Field": "(all checks)", "Source": "Backend checks",
                             "Source row": "—", "Verdict": "PASS",
                             "Finding": "All built-in checks passed.", "Fix": "—"})
    return findings
