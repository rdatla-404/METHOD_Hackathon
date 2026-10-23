# Submission headers get truncated in screenshots, so we match columns by PREFIX.
# "requested_voltage_k" and "requested_voltage_kv" both resolve to "voltage".
FIELD_PREFIX = {
    "applicant":  "applicant_name",
    "project":    "project_name",
    "type":       "facility_type",
    "capacity":   "nameplate_capacity",
    "poi":        "poi_substation",
    "voltage":    "requested_voltage",
    "gentie_req": "gen_tie_required",
    "gentie_len": "gen_tie_length",
    "inservice":  "requested_inservice",
    "dep_sub":    "deposit_submitted",
    "dep_amt":    "deposit_amount",
}
PENALTY = {"blocker": 25, "warning": 8, "info": 0}

# Reference tables are found by the columns they contain, not by file name.
SUBSTATION_COLS = ["substation_name", "rated_voltage_kv", "available_hosting_capacity_mw"]
APPLICANT_COLS = ["applicant_name", "status"]

# ---- NE-RTO intake policy (client rules from the brief, not reference data) ----
ALLOWED_FACILITY_TYPES = ("wind", "solar", "hydro")
FACILITY_ALIASES = {"water": "hydro"}   # the client's sample data uses "Water" for hydro
# Gen-tie length must be STRICTLY below these limits (miles).
GEN_TIE_MAX_MILES = {"solar": 15, "wind": 15, "hydro": 25}
MIN_INSERVICE_YEARS = 2          # in-service date must be >= today + 2 years
# Required deposit: below 20 MW -> $10K; 20 to 100 MW inclusive -> $50K; above 100 MW -> $150K
DEPOSIT_SMALL_BELOW_MW = 20
DEPOSIT_LARGE_ABOVE_MW = 100
DEPOSIT_AMOUNTS = {"small": 10_000, "medium": 50_000, "large": 150_000}