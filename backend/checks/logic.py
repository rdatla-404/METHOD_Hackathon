"""Checks that need no reference data: completeness, format, internal consistency, policy."""
import pandas as pd
from ..models import Issue, BLOCKER, INFO
from ..config import (FIELD_PREFIX, ALLOWED_FACILITY_TYPES, FACILITY_ALIASES, GEN_TIE_MAX_MILES,
                      MIN_INSERVICE_YEARS, DEPOSIT_SMALL_BELOW_MW,
                      DEPOSIT_LARGE_ABOVE_MW, DEPOSIT_AMOUNTS)
from ..fields import blank, yes, no, num, norm, get
from . import check

INTERNAL = "Submission (internal consistency)"
POLICY = "NE-RTO intake policy"


def _facility(sub):
    """Normalised facility type if it is an allowed one, else None."""
    _, val = get(sub, "type")
    k = FACILITY_ALIASES.get(norm(val), norm(val))
    return k if k in ALLOWED_FACILITY_TYPES else None


def required_deposit(mw):
    if mw < DEPOSIT_SMALL_BELOW_MW:
        return DEPOSIT_AMOUNTS["small"]
    if mw <= DEPOSIT_LARGE_ABOVE_MW:
        return DEPOSIT_AMOUNTS["medium"]
    return DEPOSIT_AMOUNTS["large"]


@check("All required fields are filled in")
def required_fields(sub, ref):
    out = []
    _, req = get(sub, "gentie_req")
    for key in FIELD_PREFIX:
        col, val = get(sub, key)
        if key == "gentie_len" and no(req):   # "No" gen-tie: an empty length means 0
            continue
        if blank(val):
            out.append(Issue("required_fields", BLOCKER, col, f"'{col}' is missing.",
                             f"Provide a value for {col}.", "Submission (completeness)"))
    return out


@check("Facility type is wind, solar or hydro")
def facility_type(sub, ref):
    col, val = get(sub, "type")
    if blank(val):
        return None
    if _facility(sub) is None:
        return [Issue("facility_type", BLOCKER, col,
                      f"'{val}' is not an eligible facility type.",
                      "Only wind, solar or hydro projects can be submitted.", POLICY,
                      suggestions=list(t.title() for t in ALLOWED_FACILITY_TYPES))]
    return []


@check("Nameplate capacity is a positive number (MW)")
def capacity_numeric(sub, ref):
    col, val = get(sub, "capacity")
    if blank(val):
        return None
    n = num(val)
    if n is None or n <= 0:
        return [Issue("capacity_numeric", BLOCKER, col, "Capacity must be a positive number.",
                      "Enter nameplate capacity in MW.", "Submission (format)")]
    return []


@check("Gen-tie: required = Yes → length > 0; No → length = 0")
def gen_tie_consistency(sub, ref):
    rc, req = get(sub, "gentie_req")
    lc, length = get(sub, "gentie_len")
    if blank(req):
        return None
    if not (yes(req) or no(req)):
        return [Issue("gen_tie_consistency", BLOCKER, rc, f"'{req}' is not Yes or No.",
                      "Answer Yes or No.", "Submission (format)")]
    n = 0.0 if blank(length) else num(length)
    if n is None or n < 0:
        return [Issue("gen_tie_consistency", BLOCKER, lc, "Gen-tie length must be a number of miles, 0 or more.",
                      "Enter the length in miles.", "Submission (format)")]
    if yes(req) and n <= 0:
        return [Issue("gen_tie_consistency", BLOCKER, lc,
                      "Gen-tie is marked required but its length is 0 or empty.",
                      f"Enter the gen-tie length, or set {rc} to No.", INTERNAL)]
    if no(req) and n > 0:
        return [Issue("gen_tie_consistency", BLOCKER, lc,
                      f"Gen-tie is marked not required but a length of {n:g} miles is given.",
                      f"Set the length to 0, or set {rc} to Yes.", INTERNAL)]
    return []


@check("Gen-tie length is under the limit for the facility type (solar/wind < 15 mi, hydro < 25 mi)")
def gen_tie_max(sub, ref):
    lc, length = get(sub, "gentie_len")
    kind = _facility(sub)
    n = num(length)
    if kind is None or n is None:
        return None
    limit = GEN_TIE_MAX_MILES[kind]
    if n >= limit:
        return [Issue("gen_tie_max", BLOCKER, lc,
                      f"A {kind} project's gen-tie must be under {limit} miles; this one is {n:g}.",
                      f"Shorten the gen-tie to less than {limit} miles or choose a closer substation.", POLICY)]
    return []


@check("In-service date is at least 2 years from today")
def inservice_date(sub, ref):
    col, raw = get(sub, "inservice")
    if blank(raw):
        return None
    try:
        d = pd.to_datetime(raw).date()
    except Exception:
        return [Issue("inservice_date", BLOCKER, col, f"'{raw}' is not a valid date.",
                      "Use the format YYYY-MM-DD.", "Submission (format)")]
    earliest = (pd.Timestamp.today().normalize() + pd.DateOffset(years=MIN_INSERVICE_YEARS)).date()
    if d < earliest:
        return [Issue("inservice_date", BLOCKER, col,
                      f"In-service date {d} is earlier than {earliest}, the minimum "
                      f"({MIN_INSERVICE_YEARS} years from today).",
                      f"Choose a date on or after {earliest}.", POLICY)]
    return []


@check("Deposit has been submitted")
def deposit_submitted(sub, ref):
    fc, flag = get(sub, "dep_sub")
    if blank(flag):
        return None
    if yes(flag):
        return []
    if no(flag):
        return [Issue("deposit_submitted", BLOCKER, fc, "Deposit has not been submitted.",
                      "Submit the deposit before filing the request.", INTERNAL)]
    return [Issue("deposit_submitted", BLOCKER, fc, f"'{flag}' is not Yes or No.",
                  "Answer Yes or No.", "Submission (format)")]


@check("Deposit covers the requirement (<20 MW $10K · 20–100 MW $50K · >100 MW $150K)")
def deposit_amount(sub, ref):
    _, flag = get(sub, "dep_sub")
    cc, cap = get(sub, "capacity")
    ac, amt = get(sub, "dep_amt")
    mw = num(cap)
    if not yes(flag) or mw is None or mw <= 0:
        return None
    if blank(amt):
        return None   # reported by required_fields
    paid = num(amt)
    if paid is None or paid <= 0:
        return [Issue("deposit_amount", BLOCKER, ac, "Deposit is marked submitted but the amount is missing or 0.",
                      "Enter the deposit amount you paid.", INTERNAL)]
    need = required_deposit(mw)
    if paid < need:
        return [Issue("deposit_amount", BLOCKER, ac,
                      f"A {mw:g} MW project requires a ${need:,.0f} deposit; ${paid:,.0f} was entered.",
                      f"Pay and enter at least ${need:,.0f}.", POLICY)]
    if paid > need:   # accepted, but flagged for the intake team
        return [Issue("deposit_amount", INFO, ac,
                      f"Deposit of ${paid:,.0f} is more than the ${need:,.0f} required for a {mw:g} MW project. "
                      "Accepted, but flagged.",
                      f"Confirm ${paid:,.0f} is intended; the requirement is ${need:,.0f}.", POLICY)]
    return []