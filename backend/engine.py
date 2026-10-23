from dataclasses import asdict
from typing import Optional, Dict, Any
from .checks import CHECKS
from .config import PENALTY
from .loader import load_reference

def validate(submission: dict, ref: Optional[Dict[str, Any]] = None) -> dict:
    ref = ref if ref is not None else load_reference()
    issues = [i for c in CHECKS for i in c(submission, ref)]
    score = max(0, 100 - sum(PENALTY[i.severity] for i in issues))
    if any(i.severity == "blocker" for i in issues):
        verdict = "NOT READY"
    else:
        verdict = "NEEDS FIXES" if issues else "READY"
    return {"score": score, "verdict": verdict, "issues": [asdict(i) for i in issues]}