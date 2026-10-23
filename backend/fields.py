import re
import pandas as pd
from .config import FIELD_PREFIX


def blank(v):
    return v is None or (not isinstance(v, str) and pd.isna(v)) or str(v).strip() == ""


def yes(v):
    return str(v).strip().lower() in ("yes", "y", "true", "1")


def num(v):
    """float or None."""
    if blank(v):
        return None
    out = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
    return None if pd.isna(out) else float(out)


def norm(v):
    """Case-, whitespace- and punctuation-insensitive key for exact matching."""
    return re.sub(r"\s+", " ", str(v)).strip().casefold() if not blank(v) else ""


def get(sub, key):
    """(actual_column_name, value) for a logical field, matched by prefix."""
    prefix = FIELD_PREFIX[key]
    for col in sub:
        if str(col).strip().lower().startswith(prefix):
            return str(col), sub[col]
    return prefix, None


def find_table(ref, needs):
    """Find the loaded extract that has all `needs` columns. -> (name, df|None)."""
    for name, df in (ref or {}).items():
        d = df.rename(columns=lambda c: str(c).strip().lower())
        if set(needs) <= set(d.columns):
            return name, d
    return None, None


def src_label(table_name, column):
    return f"{table_name} → {column}"
