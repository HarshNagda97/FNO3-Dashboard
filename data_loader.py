"""
NSE FNO3 Data Loader
---------------------
Reads all MWPL_Report_*.xls files from a folder, validates their structure,
and combines them into one clean master dataset.

Run this with:  python data_loader.py
"""

import pandas as pd
import os
import re
from datetime import datetime

# ====== SETTINGS — change this if your folder is named differently ======
FOLDER_PATH = "nse_reports"   # folder containing all the .xls files
OUTPUT_FILE = "master_data.csv"  # combined clean dataset gets saved here
# ===========================================================================


def extract_date_from_filename(filename):
    """
    Extracts date from filenames in either format:
      - 'MWPL_Report_27Feb2026.xls'   (no dashes)
      - 'MWPL_Report_01-Apr-2026.xls' (with dashes)
    Returns a datetime.date object, or None if pattern doesn't match.
    """
    # Try dashed format first: DD-Mon-YYYY
    match = re.search(r'(\d{1,2}-[A-Za-z]{3}-\d{4})', filename)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d-%b-%Y").date()
        except ValueError:
            pass

    # Fall back to no-dash format: DDMonYYYY
    match = re.search(r'(\d{1,2}[A-Za-z]{3}\d{4})', filename)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d%b%Y").date()
        except ValueError:
            pass

    return None


def load_single_file(filepath, filename):
    """
    Loads one FNO3 .xls file and returns a tidy DataFrame:
    columns -> Date, Stock, Num_Clients, Sum_Pct
    Also returns a dict of validation info for this file.
    """
    info = {"filename": filename, "status": "OK", "error": None,
             "rows": 0, "client_cols": 0, "date": None}

    file_date = extract_date_from_filename(filename)
    if file_date is None:
        info["status"] = "FAILED"
        info["error"] = "Could not extract date from filename"
        return None, info
    info["date"] = file_date

    try:
        df = pd.read_excel(filepath, header=1)
    except Exception as e:
        info["status"] = "FAILED"
        info["error"] = f"Could not read file: {e}"
        return None, info

    # Basic structure check
    if "Underlying Stock" not in df.columns:
        info["status"] = "FAILED"
        info["error"] = "Missing 'Underlying Stock' column — header row may be wrong"
        return None, info

    # Dynamically find all "Client N" columns (handles 12, 13, or any other count)
    client_cols = [c for c in df.columns if str(c).strip().startswith("Client")]
    info["client_cols"] = len(client_cols)

    if len(client_cols) == 0:
        info["status"] = "FAILED"
        info["error"] = "No 'Client' columns found"
        return None, info

    # Drop rows with no stock name (safety net for stray blank rows)
    df = df.dropna(subset=["Underlying Stock"])

    # Compute Num_Clients (count of non-NaN client values) and Sum_Pct (sum of them)
    client_data = df[client_cols]
    num_clients = client_data.notna().sum(axis=1)
    sum_pct = client_data.sum(axis=1, skipna=True)

    tidy = pd.DataFrame({
        "Date": file_date,
        "Stock": df["Underlying Stock"].astype(str).str.strip(),
        "Num_Clients": num_clients,
        "Sum_Pct": sum_pct.round(2)
    })

    info["rows"] = len(tidy)
    return tidy, info


def main():
    if not os.path.isdir(FOLDER_PATH):
        print(f"ERROR: Folder '{FOLDER_PATH}' not found. "
              f"Make sure this script is placed one level above that folder, "
              f"or update FOLDER_PATH at the top of this script.")
        return

    all_files = sorted([f for f in os.listdir(FOLDER_PATH) if f.lower().endswith(".xls")])

    if len(all_files) == 0:
        print(f"ERROR: No .xls files found in '{FOLDER_PATH}'.")
        return

    print(f"Found {len(all_files)} .xls files. Processing...\n")

    all_data = []
    file_infos = []

    for fname in all_files:
        fpath = os.path.join(FOLDER_PATH, fname)
        tidy_df, info = load_single_file(fpath, fname)
        file_infos.append(info)
        if tidy_df is not None:
            all_data.append(tidy_df)

    # ---------- Build validation summary ----------
    ok_files = [i for i in file_infos if i["status"] == "OK"]
    failed_files = [i for i in file_infos if i["status"] == "FAILED"]
    client_col_counts = sorted(set(i["client_cols"] for i in ok_files))
    dates_found = sorted(set(i["date"] for i in ok_files))

    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total files found:        {len(all_files)}")
    print(f"Successfully processed:   {len(ok_files)}")
    print(f"Failed:                   {len(failed_files)}")
    print(f"Distinct 'Client N' counts seen across files: {client_col_counts}")
    if dates_found:
        print(f"Date range covered:       {dates_found[0]} to {dates_found[-1]}")
        # Check for duplicate dates (two files mapping to same date)
        if len(dates_found) != len(ok_files):
            print(f"WARNING: Found duplicate dates! "
                  f"{len(ok_files)} files but only {len(dates_found)} unique dates.")
    print()

    if failed_files:
        print("FAILED FILES (needs attention):")
        for f in failed_files:
            print(f"  - {f['filename']}: {f['error']}")
        print()

    if not all_data:
        print("No data could be loaded. Stopping.")
        return

    # ---------- Combine everything ----------
    master_df = pd.concat(all_data, ignore_index=True)

    # Check for any duplicate (Date, Stock) pairs — would indicate a real problem
    dupes = master_df.duplicated(subset=["Date", "Stock"]).sum()
    print(f"Duplicate (Date, Stock) rows in combined data: {dupes}")

    # Unique stock count across entire period
    unique_stocks = master_df["Stock"].nunique()
    print(f"Unique stocks seen across ALL files: {unique_stocks}")

    # Save the master file
    master_df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nMaster dataset saved to: {OUTPUT_FILE}")
    print(f"Total rows in master dataset: {len(master_df)}")
    print("\nDone. Please copy everything above this line and paste it back to Claude.")


if __name__ == "__main__":
    main()
