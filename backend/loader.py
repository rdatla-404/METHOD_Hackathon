"""Loads the NE-RTO extracts that ship with the backend (data/). Users never upload these."""
import hashlib
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_cache = None


def load_reference():
    """Load every CSV/XLSX in data/ as DataFrames keyed by file name. Empty is fine."""
    global _cache
    if _cache is None:
        _cache = {}
        for p in sorted(DATA_DIR.glob("*")):
            if p.suffix == ".csv":
                _cache[p.name] = pd.read_csv(p, dtype=object)
            elif p.suffix in (".xlsx", ".xls"):
                _cache[p.name] = pd.read_excel(p, dtype=object)  # first sheet
    return _cache


def reference_fingerprint():
    """{file name: sha256} of the extracts in use, recorded with every check for audit."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(DATA_DIR.glob("*")) if p.suffix in (".csv", ".xlsx", ".xls")}