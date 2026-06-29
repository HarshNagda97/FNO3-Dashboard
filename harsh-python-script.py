import os
import re
import time
import random
from datetime import datetime, timedelta

import requests
import pandas as pd
import yfinance as yf

# ==========================================
# CONSTANTS & CONFIGURATION
# ==========================================
START_DATE = "2026-01-01"   # only used if nse_reports folder is empty
OUTPUT_DIR = "nse_reports"
MASTER_DATA_FILE = "master_data.csv"
PRICE_DATA_FILE = "price_data.csv"
MAX_RETRIES = 3
# ==========================================


# ============================================================
# PART 1 — Figure out which dates we actually need
# ============================================================

def extract_date_from_filename(filename):
    """Handles both dashed (01-Jun-2026) and non-dashed (01Jun2026) formats."""
    match = re.search(r'(\d{1,2}-[A-Za-z]{3}-\d{4})', filename)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d-%b-%Y").date()
        except ValueError:
            pass
    match = re.search(r'(\d{1,2}[A-Za-z]{3}\d{4})', filename)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d%b%Y").date()
        except ValueError:
            pass
    return None


def get_existing_dates(folder):
    """Returns the set of dates we already have files for."""
    existing = set()
    if not os.path.isdir(folder):
        return existing
    for fname in os.listdir(folder):
        if fname.lower().endswith(".xls"):
            d = extract_date_from_filename(fname)
            if d:
                existing.add(d)
    return existing


def get_dates_to_fetch(existing_dates):
    """
    Builds list of dates to fetch:
    - Starts from day after latest existing file (or START_DATE if folder empty)
    - Goes up to today
    - Skips weekends
    - Skips dates already downloaded
    """
    if existing_dates:
        fetch_from = max(existing_dates) + timedelta(days=1)
    else:
        fetch_from = datetime.strptime(START_DATE, "%Y-%m-%d").date()

    fetch_to = datetime.now().date()

    dates_to_try = []
    current = fetch_from
    while current <= fetch_to:
        if current.weekday() < 5:  # skip Saturday=5, Sunday=6
            if current not in existing_dates:
                dates_to_try.append(current)
        current += timedelta(days=1)

    return dates_to_try


# ============================================================
# PART 2 — Download files from NSE
# ============================================================

def build_session():
    """Creates a requests session with NSE cookies established."""
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    session.headers.update(headers)
    session.get("https://www.nseindia.com/", timeout=30)
    time.sleep(random.uniform(0.5, 1.0))
    session.get("https://www.nseindia.com/all-reports-derivatives", timeout=30)
    time.sleep(random.uniform(0.5, 1.0))
    return session


def download_one_date(session, date_obj):
    """
    Downloads FNO3 file for one date with retries.
    Returns (success, file_path or None, message)
    """
    date_str = date_obj.strftime("%d-%b-%Y")
    url = (
        "https://www.nseindia.com/api/reports?archives=%5B%7B%22name%22%3A%22"
        "F%26O%20-%20Clients%20Position%20%25%20greater%20than%20equal%20to%20"
        "3%25%20of%20Stock%20MWPL(xls)%22%2C%22type%22%3A%22archives%22%2C"
        "%22category%22%3A%22derivatives%22%2C%22section%22%3A%22equity%22%7D%5D"
        f"&date={date_str}&type=equity&mode=single"
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=30)
            if response.status_code == 200 and len(response.content) > 0:
                file_name = f"MWPL_Report_{date_str}.xls"
                file_path = os.path.join(OUTPUT_DIR, file_name)
                with open(file_path, "wb") as f:
                    f.write(response.content)
                return True, file_path, "OK"
            else:
                last_error = f"Status code {response.status_code}"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES:
            time.sleep(2 * attempt)

    return False, None, last_error


def fetch_new_files():
    """Main download phase. Returns list of newly downloaded dates."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    existing_dates = get_existing_dates(OUTPUT_DIR)
    dates_to_try = get_dates_to_fetch(existing_dates)

    print(f"Already have files for {len(existing_dates)} dates.")
    print(f"Need to check {len(dates_to_try)} new date(s) (weekends excluded).\n")

    if not dates_to_try:
        print("Nothing new to fetch. All caught up.")
        return []

    print("Initializing NSE session...")
    session = build_session()

    newly_downloaded = []
    not_yet_published = []

    for date_obj in dates_to_try:
        date_str = date_obj.strftime("%d-%b-%Y")
        print(f"Fetching {date_str}...", end=" ")
        success, file_path, message = download_one_date(session, date_obj)

        if success:
            print(f"OK -> {file_path}")
            newly_downloaded.append(date_obj)
        else:
            if date_obj == datetime.now().date():
                print("Not available yet (NSE may not have published today's file).")
                not_yet_published.append(date_obj)
            else:
                print(f"FAILED - {message}")

        time.sleep(random.uniform(1.0, 2.0))

    print(f"\nNewly downloaded: {len(newly_downloaded)} file(s).")
    if not_yet_published:
        print(f"Not yet published: {len(not_yet_published)} date(s).")

    return newly_downloaded


# ============================================================
# PART 3 — Refresh master_data.csv
# ============================================================

def load_single_file(filepath, filename):
    """Reads one XLS file and returns a tidy DataFrame."""
    file_date = extract_date_from_filename(filename)
    if file_date is None:
        return None
    try:
        df = pd.read_excel(filepath, header=1)
    except Exception:
        return None
    if "Underlying Stock" not in df.columns:
        return None
    client_cols = [c for c in df.columns if str(c).strip().startswith("Client")]
    if len(client_cols) == 0:
        return None
    df = df.dropna(subset=["Underlying Stock"])
    client_data = df[client_cols]
    num_clients = client_data.notna().sum(axis=1)
    sum_pct = client_data.sum(axis=1, skipna=True)
    return pd.DataFrame({
        "Date": file_date,
        "Stock": df["Underlying Stock"].astype(str).str.strip(),
        "Num_Clients": num_clients,
        "Sum_Pct": sum_pct.round(2)
    })


def refresh_master_data():
    """Rebuilds master_data.csv from ALL files in nse_reports/."""
    print("\nRefreshing master_data.csv...")
    all_files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".xls")])
    all_data = []
    for fname in all_files:
        tidy = load_single_file(os.path.join(OUTPUT_DIR, fname), fname)
        if tidy is not None:
            all_data.append(tidy)
    if not all_data:
        print("No data found. Skipping.")
        return
    master_df = pd.concat(all_data, ignore_index=True)
    master_df = master_df.drop_duplicates(subset=["Date", "Stock"])
    master_df.to_csv(MASTER_DATA_FILE, index=False)
    print(f"master_data.csv updated. Total rows: {len(master_df)}")


# ============================================================
# PART 4 — Refresh price_data.csv
# ============================================================

def refresh_price_data(newly_downloaded_dates):
    """Fetches prices only for newly downloaded dates and appends to price_data.csv."""
    if not newly_downloaded_dates:
        print("\nNo new dates downloaded. Skipping price refresh.")
        return

    print("\nRefreshing price_data.csv for new dates...")

    if not os.path.exists(MASTER_DATA_FILE):
        print("master_data.csv not found. Skipping price refresh.")
        return

    master_df = pd.read_csv(MASTER_DATA_FILE, parse_dates=["Date"])
    fetch_start = min(newly_downloaded_dates)
    fetch_end = max(newly_downloaded_dates)

    relevant_stocks = sorted(
        master_df[master_df["Date"].dt.date.isin(newly_downloaded_dates)]["Stock"].unique()
    )

    print(f"Fetching prices for {len(relevant_stocks)} stocks, {fetch_start} to {fetch_end}...")

    new_price_rows = []
    failed = []

    for stock in relevant_stocks:
        ticker = f"{stock}.NS"
        try:
            data = yf.download(
                ticker,
                start=fetch_start,
                end=fetch_end + timedelta(days=1),
                progress=False,
                auto_adjust=True
            )
            if data is None or data.empty:
                failed.append(stock)
                continue
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            for idx in range(len(data)):
                new_price_rows.append({
                    "Date": data.index[idx].date(),
                    "Stock": stock,
                    "Close": data["Close"].iloc[idx]
                })
        except Exception:
            failed.append(stock)
        time.sleep(0.3)

    if failed:
        print(f"Could not fetch prices for: {', '.join(failed[:10])}"
              f"{'...' if len(failed) > 10 else ''}")

    if not new_price_rows:
        print("No new price rows fetched.")
        return

    new_price_df = pd.DataFrame(new_price_rows)

    if os.path.exists(PRICE_DATA_FILE):
        existing_price_df = pd.read_csv(PRICE_DATA_FILE, parse_dates=["Date"])
        existing_price_df["Date"] = existing_price_df["Date"].dt.date
        combined = pd.concat([existing_price_df, new_price_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Date", "Stock"], keep="last")
    else:
        combined = new_price_df

    combined.to_csv(PRICE_DATA_FILE, index=False)
    print(f"price_data.csv updated. Total rows: {len(combined)}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("NSE FNO3 AUTO-FETCH")
    print("=" * 60)
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    newly_downloaded = fetch_new_files()
    refresh_master_data()
    refresh_price_data(newly_downloaded)

    print("\n" + "=" * 60)
    print("DONE. Dashboard data is up to date.")
    print("=" * 60)


if __name__ == "__main__":
    main()