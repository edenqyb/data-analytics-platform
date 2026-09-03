from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DATA = ROOT / "data" / "2016.xlsx"
OUTPUT_DATA = ROOT / "data" / "source_data.csv"

CATEGORIES = {
    "cat1": ["in_progress", "invoice_prep", "at_hq", "at_finance", "total"],
    "cat2": ["in_progress", "invoice_prep", "at_hq", "at_finance", "total"],
    "cat3": ["in_progress", "invoice_prep", "at_hq", "at_finance", "total"],
    "cat4": [
        "in_progress",
        "invoice_prep",
        "at_consultant",
        "at_hq",
        "at_finance",
        "total",
    ],
    "cat5": [
        "in_progress",
        "invoice_prep",
        "at_consultant",
        "at_hq",
        "at_finance",
        "total",
    ],
    "cat6": [
        "in_progress",
        "invoice_prep",
        "at_consultant",
        "at_hq",
        "at_finance",
        "total",
    ],
    "cat7": [
        "in_progress",
        "invoice_prep",
        "at_consultant",
        "at_hq",
        "at_finance",
        "total",
    ],
}

# totals for each category
CAT_TOTALS = [
    "cat_in_progress",
    "cat_invoice_prep",
    "cat_at_consultant",
    "cat_at_hq",
    "cat_at_finance",
    "cat_total",
]

# dropping these rows
SUBTOTAL_NAME = "جمع به تفکیک هر واحد"
COMPANY_TOTAL_NAME = "کل شرکت"
COMPANY_SENTINEL_CODE = 9999


def build_column_names():
    cols = ["name", "code", "year", "month"]
    for category, suffixes in CATEGORIES.items():
        cols.extend(f"{category}_{suffix}" for suffix in suffixes)
    cols.extend(CAT_TOTALS)
    return cols


def main():
    raw = pd.read_excel(SOURCE_DATA, header=None)
    print(f"raw shape: {raw.shape}")
    print(f"raw row 1: {raw.iloc[1].tolist()}")
    print(f"raw row 2: {raw.iloc[2].tolist()}")

    data = raw.iloc[3:].reset_index(drop=True)
    data = data.dropna(how="all")

    col_names = build_column_names()
    assert len(col_names) == data.shape[1], (
        f"column count mismatch: expected {len(col_names)}, got {data.shape[1]}"
    )
    data.columns = col_names

    name = data["name"].astype(str).str.strip()
    data = data[
        ~name.isin([SUBTOTAL_NAME, COMPANY_TOTAL_NAME])
        & (data["code"] != COMPANY_SENTINEL_CODE)
    ].reset_index(drop=True)

    # postgres copy
    numeric_cols = [c for c in col_names if c not in ("name")]
    data[numeric_cols] = data[numeric_cols].apply(pd.to_numeric, errors="coerce").astype("Int64")

    print(f"data dtypes: {data.dtypes}")

    OUTPUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUTPUT_DATA, index=False, encoding="utf-8")

if __name__ == "__main__":
    main()
