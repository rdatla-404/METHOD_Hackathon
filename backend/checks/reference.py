"""Checks driven by the NE-RTO extracts. No reference values are typed in here:
everything is looked up in the loaded tables at runtime."""
import difflib
from ..models import Issue, BLOCKER, WARNING
from ..config import SUBSTATION_COLS, APPLICANT_COLS
from ..fields import blank, num, norm, get, find_table, src_label
from . import check


def _closest(value, candidates, n=3):
    pool = {norm(c): c for c in candidates}
    hits = difflib.get_close_matches(norm(value), list(pool), n=n, cutoff=0.6)
    return [pool[h] for h in hits]


def _no_table(check_name, field, needs):
    return Issue(check_name, WARNING, field,
                 f"Could not verify: no reference extract with columns {needs} is loaded.",
                 "Upload the NE-RTO extract and check again.", "Reference data unavailable")


def _match_substation(sub, ref):
    col, val = get(sub, "poi")
    if blank(val):
        return "skip", None
    tname, df = find_table(ref, SUBSTATION_COLS)
    if df is None:
        return "notable", None
    hit = df[df["substation_name"].map(norm) == norm(val)]
    if hit.empty:
        return "notfound", (col, val, tname, df)
    return "ok", (col, val, tname, df, hit.index[0])


@check
def applicant_registered(sub, ref):
    col, val = get(sub, "applicant")
    if blank(val):
        return []
    tname, df = find_table(ref, APPLICANT_COLS)
    if df is None:
        return [_no_table("applicant_registered", col, APPLICANT_COLS)]
    hit = df[df["applicant_name"].map(norm) == norm(val)]
    src = src_label(tname, "applicant_name / status")
    if hit.empty:
        return [Issue("applicant_registered", BLOCKER, col,
                      f"'{val}' is not a registered applicant.",
                      "Register the company first, or correct the name to match your registration exactly.",
                      src, suggestions=_closest(val, df["applicant_name"]))]
    i = hit.index[0]
    status = str(hit.loc[i, "status"]).strip()
    row = str(i + 2)
    if status.casefold() == "suspended":
        return [Issue("applicant_registered", BLOCKER, col,
                      f"'{val}' is registered but its status is Suspended.",
                      "Resolve the suspension with NE-RTO before submitting.", src, row)]
    if status.casefold() != "active":
        return [Issue("applicant_registered", WARNING, col,
                      f"'{val}' has registration status '{status}', not Active.",
                      "Confirm with NE-RTO that a non-Active registration can file.", src, row)]
    return []


@check
def poi_exists(sub, ref):
    state, ctx = _match_substation(sub, ref)
    if state == "notable":
        return [_no_table("poi_exists", get(sub, "poi")[0], SUBSTATION_COLS)]
    if state != "notfound":
        return []
    col, val, tname, df = ctx
    return [Issue("poi_exists", BLOCKER, col, f"'{val}' is not a known substation.",
                  "Pick a point of interconnection from the NE-RTO substation list.",
                  src_label(tname, "substation_name"),
                  suggestions=_closest(val, df["substation_name"]))]


@check
def voltage_matches(sub, ref):
    state, ctx = _match_substation(sub, ref)
    if state == "notable":
        return [_no_table("voltage_matches", get(sub, "poi")[0], SUBSTATION_COLS)]
    if state != "ok":
        return []
    _, poi, tname, df, i = ctx
    vcol, vval = get(sub, "voltage")
    v = num(vval)
    if v is None:
        return []
    rated = float(df.loc[i, "rated_voltage_kv"])
    if v == rated:
        return []
    same_v = df[df["rated_voltage_kv"].astype(float) == v]["substation_name"].tolist()[:3]
    return [Issue("voltage_matches", BLOCKER, vcol,
                  f"{poi} is rated {rated:g} kV but the request is for {v:g} kV.",
                  f"Change the requested voltage to {rated:g} kV"
                  + (f", or choose a {v:g} kV substation." if same_v else "."),
                  src_label(tname, "rated_voltage_kv"), str(i + 2), suggestions=same_v)]


@check
def capacity_fits(sub, ref):
    state, ctx = _match_substation(sub, ref)
    if state == "notable":
        return [_no_table("capacity_fits", get(sub, "poi")[0], SUBSTATION_COLS)]
    if state != "ok":
        return []
    _, poi, tname, df, i = ctx
    ccol, cval = get(sub, "capacity")
    mw = num(cval)
    if mw is None or mw <= 0:
        return []
    room = float(df.loc[i, "available_hosting_capacity_mw"])
    if mw <= room:
        return []
    vcol, vval = get(sub, "voltage")
    v = num(vval) or float(df.loc[i, "rated_voltage_kv"])
    alt = df[(df["rated_voltage_kv"].astype(float) == v)
             & (df["available_hosting_capacity_mw"].astype(float) >= mw)]
    alt = alt.sort_values("available_hosting_capacity_mw")["substation_name"].tolist()[:3]
    unit_hint = " Check you entered MW, not kW." if mw > df["available_hosting_capacity_mw"].astype(float).max() else ""
    return [Issue("capacity_fits", BLOCKER, ccol,
                  f"{mw:g} MW exceeds the {room:g} MW available at {poi}.",
                  f"Reduce the capacity to {room:g} MW or less"
                  + (f", or pick a {v:g} kV substation with enough room." if alt else ", or split the project.")
                  + unit_hint,
                  src_label(tname, "available_hosting_capacity_mw"), str(i + 2), suggestions=alt)]
