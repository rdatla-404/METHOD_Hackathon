"""Turns a submission file (DataFrame) into the result the UI shows."""
import pandas as pd
from .checks import CHECKS
from .engine import validate

ONE_ROW = "Exactly one request per file"


def run_precheck(submission: pd.DataFrame, ref=None) -> dict:
    """-> {verdict, constraints[], findings[]}. Rejects files with 0 or >1 data rows."""
    df = submission.dropna(how="all")
    n = len(df)
    if n != 1:
        msg = "The file has no data rows." if n == 0 else f"The file has {n} rows; only one request per file is accepted."
        return {
            "verdict": "NOT READY",
            "constraints": [{"constraint": ONE_ROW, "status": "FAIL"}]
                           + [{"constraint": c.label, "status": "NOT CHECKED"} for c in CHECKS],
            "findings": [{"Constraint": ONE_ROW, "Field": "(file)", "Severity": "blocker", "Finding": msg,
                          "Fix": "Submit a file with a single request row (plus the header).",
                          "Source": "NE-RTO intake policy", "Source row": "—"}],
        }
    row = df.iloc[0].to_dict()
    result = validate(row, ref=ref)
    label = {c.check_name: c.label for c in CHECKS}
    findings = []
    for i in result["issues"]:
        fix = i["fix"]
        if i["suggestions"]:
            fix += " Closest valid: " + ", ".join(map(str, i["suggestions"])) + "."
        findings.append({"Constraint": label[i["check"]], "Field": i["field"], "Severity": i["severity"],
                         "Finding": i["message"], "Fix": fix, "Source": i["source"],
                         "Source row": i["source_row"]})
    constraints = [{"constraint": ONE_ROW, "status": "PASS"}] + \
                  [{"constraint": c["constraint"], "status": c["status"]} for c in result["constraints"]]
    return {"verdict": result["verdict"], "constraints": constraints, "findings": findings}