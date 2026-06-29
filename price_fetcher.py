"""
NSE Stock Price Fetcher
-------------------------
Reads the unique stock list from master_data.csv (output of data_loader.py),
fetches historical daily price data for each stock via yfinance,
and saves a combined clean price dataset.

Run this with:  python price_fetcher.py

Note: This makes one network request per stock to Yahoo Finance.
With ~195 stocks, this may take a couple of minutes. That's normal.
"""

import pandas as pd
import yfinance as yf
import time

# ====== SETTINGS ======
MASTER_DATA_FILE = "master_data.csv"   # output from data_loader.py
OUTPUT_FILE = "price_data.csv"          # combined price dataset gets saved here
PAUSE_BETWEEN_REQUESTS = 0.3            # seconds to wait between each stock (avoids rate-limiting)
# ========================


def get_stock_list_and_date_range(master_file):
    """
    Reads master_data.csv to get:
      - the list of unique stocks we need prices for
      - the overall date range we need (with a small buffer on both sides)
    """
    df = pd.read_csv(master_file, parse_dates=["Date"])
    stocks = sorted(df["Stock"].unique())
    start_date = df["Date"].min()
    end_date = df["Date"].max()
    return stocks, start_date, end_date


def fetch_price_for_stock(stock_symbol, start_date, end_date):
    """
    Fetches daily price history for one stock from yfinance.
    Returns a tidy DataFrame (Date, Stock, Close) or None if it fails.
    """
    ticker = f"{stock_symbol}.NS"
    try:
        # yfinance's 'end' is exclusive, so add a day buffer to include the last date
        data = yf.download(
            ticker,
            start=start_date,
            end=end_date + pd.Timedelta(days=1),
            progress=False,
            auto_adjust=True
        )
    except Exception as e:
        return None, str(e)

    if data is None or data.empty:
        return None, "No data returned (possibly delisted, renamed, or wrong ticker)"

    # yfinance sometimes returns multi-level columns — flatten if needed
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    tidy = pd.DataFrame({
        "Date": data.index.date,
        "Stock": stock_symbol,
        "Close": data["Close"].values
    })
    return tidy, None


def main():
    print("Reading stock list from master_data.csv...")
    stocks, start_date, end_date = get_stock_list_and_date_range(MASTER_DATA_FILE)
    print(f"Found {len(stocks)} unique stocks. Date range needed: {start_date.date()} to {end_date.date()}\n")

    all_price_data = []
    failed_stocks = []

    for i, stock in enumerate(stocks, 1):
        print(f"[{i}/{len(stocks)}] Fetching {stock}...", end=" ")
        tidy, error = fetch_price_for_stock(stock, start_date, end_date)
        if tidy is not None:
            all_price_data.append(tidy)
            print(f"OK ({len(tidy)} rows)")
        else:
            failed_stocks.append((stock, error))
            print(f"FAILED - {error}")
        time.sleep(PAUSE_BETWEEN_REQUESTS)

    print("\n" + "=" * 60)
    print("PRICE FETCH SUMMARY")
    print("=" * 60)
    print(f"Total stocks attempted:   {len(stocks)}")
    print(f"Successfully fetched:     {len(all_price_data)}")
    print(f"Failed:                   {len(failed_stocks)}")

    if failed_stocks:
        print("\nFAILED STOCKS (needs attention):")
        for stock, error in failed_stocks:
            print(f"  - {stock}: {error}")

    if not all_price_data:
        print("\nNo price data could be fetched. Stopping.")
        return

    combined = pd.concat(all_price_data, ignore_index=True)
    combined.to_csv(OUTPUT_FILE, index=False)
    print(f"\nPrice dataset saved to: {OUTPUT_FILE}")
    print(f"Total rows: {len(combined)}")
    print("\nDone. Please copy everything above this line and paste it back to Claude.")


if __name__ == "__main__":
    main()
