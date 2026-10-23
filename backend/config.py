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
