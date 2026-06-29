"""
NSE FNO3 Dashboard — Analytics Module
----------------------------------------
Core data logic, kept separate from the UI (app.py).
This module:
  1. Loads master_data.csv (FNO3: Sum%, Num Clients) and price_data.csv (Share Price)
  2. Builds the Layer 1 Master Table for any given Start/End date
  3. Applies the 4 filters with AND/OR logic

This file has NO Streamlit code in it on purpose — it can be tested
independently and reused later for Layer 2 / Layer 3.
"""

import pandas as pd


def load_data(master_file="master_data.csv", price_file="price_data.csv"):
    """
    Loads both datasets and returns them as DataFrames.
    Called once when the app starts.
    """
    fno_df = pd.read_csv(master_file, parse_dates=["Date"])
    price_df = pd.read_csv(price_file, parse_dates=["Date"])
    return fno_df, price_df


def build_master_table(fno_df, price_df, start_date, end_date):
    """
    Builds the Layer 1 Master Table for the given date range.

    For each stock, computes:
      - Sum %: Start, End, Change, Max, Min, Range
      - Num Clients: Start, End, Change, Max, Min, Range
      - Share Price: Start, End, % Change, Range %
      - Days Present (out of total FNO3-listed days in range)

    Returns a single tidy DataFrame, one row per stock.
    """
    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)

    # ---- Filter both datasets to the date range ----
    fno_range = fno_df[(fno_df["Date"] >= start_date) & (fno_df["Date"] <= end_date)]
    price_range = price_df[(price_df["Date"] >= start_date) & (price_df["Date"] <= end_date)]

    if fno_range.empty:
        return pd.DataFrame()  # no data in this range at all

    all_stocks = sorted(fno_range["Stock"].unique())
    rows = []

    for stock in all_stocks:
        stock_fno = fno_range[fno_range["Stock"] == stock].sort_values("Date")
        stock_price = price_range[price_range["Stock"] == stock].sort_values("Date")

        row = {"Stock": stock}

        # ---- Sum % metrics ----
        if not stock_fno.empty:
            sum_pct_series = stock_fno["Sum_Pct"]
            row["Sum_Pct_Start"] = sum_pct_series.iloc[0]
            row["Sum_Pct_End"] = sum_pct_series.iloc[-1]
            row["Sum_Pct_Change"] = round(row["Sum_Pct_End"] - row["Sum_Pct_Start"], 2)
            row["Sum_Pct_Max"] = sum_pct_series.max()
            row["Sum_Pct_Min"] = sum_pct_series.min()
            row["Sum_Pct_Range"] = round(row["Sum_Pct_Max"] - row["Sum_Pct_Min"], 2)
        else:
            row.update({k: None for k in
                        ["Sum_Pct_Start", "Sum_Pct_End", "Sum_Pct_Change",
                         "Sum_Pct_Max", "Sum_Pct_Min", "Sum_Pct_Range"]})

        # ---- Num Clients metrics ----
        if not stock_fno.empty:
            clients_series = stock_fno["Num_Clients"]
            row["Clients_Start"] = int(clients_series.iloc[0])
            row["Clients_End"] = int(clients_series.iloc[-1])
            row["Clients_Change"] = int(row["Clients_End"] - row["Clients_Start"])
            row["Clients_Max"] = int(clients_series.max())
            row["Clients_Min"] = int(clients_series.min())
            row["Clients_Range"] = int(row["Clients_Max"] - row["Clients_Min"])
        else:
            row.update({k: None for k in
                        ["Clients_Start", "Clients_End", "Clients_Change",
                         "Clients_Max", "Clients_Min", "Clients_Range"]})

        # ---- Share Price metrics ----
        if not stock_price.empty:
            price_series = stock_price["Close"]
            p_start = price_series.iloc[0]
            p_end = price_series.iloc[-1]
            p_max = price_series.max()
            p_min = price_series.min()
            row["Price_Start"] = round(p_start, 2)
            row["Price_End"] = round(p_end, 2)
            row["Price_Pct_Change"] = round(((p_end - p_start) / p_start) * 100, 2) if p_start else None
            row["Price_Range_Pct"] = round(((p_max - p_min) / p_min) * 100, 2) if p_min else None
        else:
            row.update({k: None for k in
                        ["Price_Start", "Price_End", "Price_Pct_Change", "Price_Range_Pct"]})

        # ---- Days Present ----
        total_days_in_range = fno_range["Date"].nunique()
        row["Days_Present"] = len(stock_fno)
        row["Total_Days_In_Range"] = total_days_in_range

        rows.append(row)

    return pd.DataFrame(rows)


def get_stock_timeseries(fno_df, price_df, stock, start_date, end_date):
    """
    Returns day-by-day time series for ONE stock, for the Layer 2 drilldown charts.

    Returns a dict with three separate DataFrames (each with a Date column):
      - "sum_pct": Date, Sum_Pct
      - "clients": Date, Num_Clients
      - "price": Date, Close
    Any of these can be empty if no data exists for that stock/range.
    """
    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)

    fno_slice = fno_df[
        (fno_df["Stock"] == stock) &
        (fno_df["Date"] >= start_date) &
        (fno_df["Date"] <= end_date)
    ].sort_values("Date")

    price_slice = price_df[
        (price_df["Stock"] == stock) &
        (price_df["Date"] >= start_date) &
        (price_df["Date"] <= end_date)
    ].sort_values("Date")

    return {
        "sum_pct": fno_slice[["Date", "Sum_Pct"]].reset_index(drop=True),
        "clients": fno_slice[["Date", "Num_Clients"]].reset_index(drop=True),
        "price": price_slice[["Date", "Close"]].reset_index(drop=True),
    }


def get_multi_stock_timeseries(fno_df, price_df, stocks, start_date, end_date):
    """
    Returns day-by-day time series for MULTIPLE stocks (Layer 3 — Compare Mode).

    Returns a dict with three DataFrames, each in "long" format
    (one row per Date+Stock combination), ready for multi-line charting:
      - "sum_pct": Date, Stock, Sum_Pct
      - "clients": Date, Stock, Num_Clients
      - "price": Date, Stock, Close
    """
    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)

    fno_slice = fno_df[
        (fno_df["Stock"].isin(stocks)) &
        (fno_df["Date"] >= start_date) &
        (fno_df["Date"] <= end_date)
    ].sort_values(["Stock", "Date"])

    price_slice = price_df[
        (price_df["Stock"].isin(stocks)) &
        (price_df["Date"] >= start_date) &
        (price_df["Date"] <= end_date)
    ].sort_values(["Stock", "Date"])

    return {
        "sum_pct": fno_slice[["Date", "Stock", "Sum_Pct"]].reset_index(drop=True),
        "clients": fno_slice[["Date", "Stock", "Num_Clients"]].reset_index(drop=True),
        "price": price_slice[["Date", "Stock", "Close"]].reset_index(drop=True),
    }


def apply_filters(df, filters, logic="AND"):
    """
    Applies up to 4 filters to the master table.

    filters: a list of dicts, each like:
        {"column": "Price_Pct_Change", "comparison": "greater", "value": 5}
        {"column": "Price_Pct_Change", "comparison": "lesser", "value": 5}
    Only ACTIVE filters (value is not None) are applied.
    logic: "AND" or "OR" — how active filters combine.

    Returns the filtered DataFrame.
    """
    active_filters = [f for f in filters if f.get("value") is not None]

    if not active_filters:
        return df  # no filters set, return everything

    masks = []
    for f in active_filters:
        col = f["column"]
        val = f["value"]
        if f["comparison"] == "greater":
            masks.append(df[col] > val)
        else:  # "lesser"
            masks.append(df[col] < val)

    if logic == "AND":
        combined_mask = masks[0]
        for m in masks[1:]:
            combined_mask &= m
    else:  # OR
        combined_mask = masks[0]
        for m in masks[1:]:
            combined_mask |= m

    return df[combined_mask]
