import pandas as pd
from backend import validate, run_backend_checks

ref = {  # same shape as app.py's `extracts`: file name -> DataFrame (dtype=object)
    "03_substation_reference_table.xlsx": pd.read_excel("data/03_substation_reference_table.xlsx", dtype=object),
    "05_registered_applicants.xlsx": pd.read_excel("data/05_registered_applicants.xlsx", dtype=object),
}
good = {"applicant_name": "Meridian Solar Partners", "project_name": "Sunfield I", "facility_type": "Solar",
        "nameplate_capacity_mw": 40, "poi_substation": "Red Rock", "requested_voltage_kv": 138,
        "gen_tie_required": "Yes", "gen_tie_length_miles": 8, "requested_inservice_date": "2029-01-15",
        "deposit_submitted": "Yes", "deposit_amount": 60000}

cases = {
  "good (the client's sample row)": {},
  "truncated headers still work": None,
  "unregistered applicant (typo)": {"applicant_name": "Meridian Solar Partner"},
  "suspended applicant": {"applicant_name": "Prairie Power"},
  "pending applicant": {"applicant_name": "Clearwater Generation"},
  "misspelled substation": {"poi_substation": "Redrock"},
  "wrong voltage": {"requested_voltage_kv": 230},
  "too big for substation": {"nameplate_capacity_mw": 150},
  "kW entered instead of MW": {"nameplate_capacity_mw": 40000},
  "case quirk (Fox ridge)": {"poi_substation": "FOX RIDGE", "requested_voltage_kv": 230, "nameplate_capacity_mw": 100},
  "gen-tie contradiction + no deposit amt + past date": {"gen_tie_length_miles": 0, "deposit_amount": None, "requested_inservice_date": "2020-01-01"},
}
for name, change in cases.items():
    if change is None:
        sub = {k[:19] if k.startswith(("requested_inservice","gen_tie_length","requested_voltage","nameplate")) else k: v for k, v in good.items()}
    else:
        sub = {**good, **change}
    r = validate(sub, ref)
    print(f"\n== {name}: {r['verdict']} (score {r['score']})")
    for i in r["issues"]:
        print(f"   [{i['severity']}] {i['check']}: {i['message']}  FIX: {i['fix']}  SRC: {i['source']} row {i['source_row']}  {i['suggestions'] or ''}")

# adapter path, using DataFrames loaded the way app.py loads them
df = pd.DataFrame([good, {**good, "poi_substation": "Redrock"}], dtype=object)
print("\n== adapter:"); [print("  ", f["Row"], f["Verdict"], f["Field"], "|", f["Finding"]) for f in run_backend_checks(df, ref)]
