from dataclasses import asdict
from typing import Optional, Dict, Any
from .checks import CHECKS
from .config import PENALTY
from .loader import load_reference


def validate(submission: dict, ref: Optional[Dict[str, Any]] = None) -> dict:
    """Run every constraint on ONE submission row (dict). Reference data defaults to data/."""
    ref = ref if ref is not None else load_reference()
    issues, constraints = [], []
    for c in CHECKS:
        found = c(submission, ref)
        if found is None:
            status, found = "NOT CHECKED", []
        elif any(i.severity == "blocker" for i in found):
            status = "FAIL"
        elif any(i.severity == "warning" for i in found):
            status = "UNVERIFIABLE"
        elif found:
            status = "FLAG"
        else:
            status = "PASS"
        constraints.append({"check": c.check_name, "constraint": c.label, "status": status})
        issues.extend(found)
    score = max(0, 100 - sum(PENALTY[i.severity] for i in issues))
    if any(i.severity == "blocker" for i in issues):
        verdict = "NOT READY"
    else:
        verdict = "NEEDS FIXES" if any(i.severity == "warning" for i in issues) else "READY"
    return {"score": score, "verdict": verdict, "constraints": constraints,
            "issues": [asdict(i) for i in issues]}