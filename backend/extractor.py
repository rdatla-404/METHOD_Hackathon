import pandas as pd


def extract_fields(uploaded_file) -> dict:
    """First row of an uploaded CSV/XLSX as a dict."""
    name = uploaded_file.name.lower()
    df = pd.read_csv(uploaded_file, dtype=object) if name.endswith(".csv") else pd.read_excel(uploaded_file, dtype=object)
    return df.iloc[0].to_dict()
