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
