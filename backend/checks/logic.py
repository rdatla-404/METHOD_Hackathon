"""Checks that need no reference data: completeness, format, internal consistency."""
from datetime import date
import pandas as pd
from ..models import Issue, BLOCKER, WARNING
from ..config import FIELD_PREFIX
from ..fields import blank, yes, num, get
from . import check

INTERNAL = "Submission (internal consistency)"


@check
def required_fields(sub, ref):
    out = []
    for key in FIELD_PREFIX:
        col, val = get(sub, key)
        if blank(val):
            out.append(Issue("required_fields", BLOCKER, col, f"'{col}' is missing.",
                             f"Provide a value for {col}.", "Submission (completeness)"))
    return out


@check
def capacity_numeric(sub, ref):
    col, val = get(sub, "capacity")
    if blank(val):
        return []
    n = num(val)
    if n is None or n <= 0:
        return [Issue("capacity_numeric", BLOCKER, col, "Capacity must be a positive number.",
                      "Enter nameplate capacity in MW.", "Submission (format)")]
    return []


@check
def gen_tie_consistency(sub, ref):
    rc, req = get(sub, "gentie_req")
    lc, length = get(sub, "gentie_len")
    if blank(req):
        return []
    n = 0.0 if blank(length) else num(length)
    if n is None:
        return [Issue("gen_tie_consistency", BLOCKER, lc, "Gen-tie length is not a number.",
                      "Enter the length in miles.", "Submission (format)")]
    if yes(req) and n <= 0:
        return [Issue("gen_tie_consistency", BLOCKER, lc,
                      "Gen-tie is marked required but its length is 0 or empty.",
                      f"Enter the gen-tie length, or set {rc} to No.", INTERNAL)]
    if not yes(req) and n > 0:
        return [Issue("gen_tie_consistency", WARNING, rc,
                      "A gen-tie length is given but gen-tie is marked not required.",
                      f"Set {rc} to Yes, or clear the length.", INTERNAL)]
    return []


@check
def deposit_consistency(sub, ref):
    fc, flag = get(sub, "dep_sub")
    ac, amt = get(sub, "dep_amt")
    n = num(amt)
    if blank(flag) or (yes(flag) and blank(amt)):
        return []  # blanks are already reported by required_fields
    if yes(flag) and (n is None or n <= 0):
        return [Issue("deposit_consistency", BLOCKER, ac,
                      "Deposit is marked submitted but the amount is missing or 0.",
                      "Enter the deposit amount you paid.", INTERNAL)]
    if not yes(flag):
        return [Issue("deposit_consistency", BLOCKER, fc,
                      "Deposit has not been submitted.",
                      "Submit the deposit before filing the request.", INTERNAL)]
    return []


@check
def inservice_date(sub, ref):
    col, raw = get(sub, "inservice")
    if blank(raw):
        return []
    try:
        d = pd.to_datetime(raw).date()
    except Exception:
        return [Issue("inservice_date", BLOCKER, col, f"'{raw}' is not a valid date.",
                      "Use the format YYYY-MM-DD.", "Submission (format)")]
    if d <= date.today():
        return [Issue("inservice_date", BLOCKER, col, "Requested in-service date is in the past.",
                      "Choose a future date.", INTERNAL)]
    return []
