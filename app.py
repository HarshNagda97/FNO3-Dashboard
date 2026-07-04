"""
NSE FNO3 Dashboard — Layer 1: Master Table
---------------------------------------------
Run this with:  streamlit run app.py

This is the main dashboard page. It shows:
  - Start Date / End Date inputs (format: D Mon YY, e.g. 3 Jul 26)
  - 4 filters in a collapsible sidebar (Greater/Lesser + value, AND/OR combine)
  - A sortable master table with the finalized 9-column view
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from analytics import load_data, build_master_table, apply_filters, get_stock_timeseries, get_multi_stock_timeseries

st.set_page_config(page_title="NSE FNO - 3% Dashboard", layout="wide")

# ---- Montserrat font + centered title styling ----
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Montserrat', sans-serif;
    }

    .block-container {
        padding-top: 2.5rem;
    }

    .centered-title {
        text-align: center;
        font-family: 'Montserrat', sans-serif;
        font-weight: 700;
        font-size: 2.5rem;
        margin-bottom: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="centered-title">NSE FNO - 3% Dashboard</div>', unsafe_allow_html=True)

# ---------- Load data once, cache it so it doesn't reload on every interaction ----------
@st.cache_data
def get_data():
    return load_data("master_data.csv", "price_data.csv")

fno_df, price_df = get_data()

overall_min_date = fno_df["Date"].min().date()
overall_max_date = fno_df["Date"].max().date()

# ============================================================
# Date Range (main page, top)
# ============================================================
date_col1, date_col2 = st.columns(2)

with date_col1:
    start_date = st.date_input(
        "Start Date", value=overall_min_date,
        min_value=overall_min_date, max_value=overall_max_date,
        format="DD/MM/YYYY"
    )

with date_col2:
    end_date = st.date_input(
        "End Date", value=overall_max_date,
        min_value=overall_min_date, max_value=overall_max_date,
        format="DD/MM/YYYY"
    )

def format_friendly_date(d):
    """Formats a date as 'D Mon YY' e.g. '3 Jul 26', working on both Windows and Mac/Linux."""
    return f"{d.day} {d.strftime('%b %y')}"

if start_date > end_date:
    st.error("Start Date must be before End Date.")
    st.stop()

# ============================================================
# Filters — collapsible sidebar
# ============================================================
filter_definitions = [
    {"label": "Share Price % Change", "column": "Price_Pct_Change"},
    {"label": "Share Price Range %", "column": "Price_Range_Pct"},
    {"label": "Sum % Change", "column": "Sum_Pct_Change"},
    {"label": "Change in No. of Clients", "column": "Clients_Change"},
]

filters = []
with st.sidebar:
    st.header("Filters")
    st.caption("Leave value blank to ignore a filter")

    for fdef in filter_definitions:
        st.markdown(f"**{fdef['label']}**")
        comparison = st.selectbox(
            "Comparison", ["Greater Than", "Lesser Than"],
            key=f"comp_{fdef['column']}", label_visibility="collapsed"
        )
        value = st.number_input(
            "Value", value=None, step=1.0,
            key=f"val_{fdef['column']}", placeholder="Leave blank to ignore"
        )
        filters.append({
            "column": fdef["column"],
            "comparison": "greater" if comparison == "Greater Than" else "lesser",
            "value": value
        })
        st.divider()

    logic = st.selectbox("Combine filters using", ["AND", "OR"])

# ============================================================
# Master Table
# ============================================================
master_table = build_master_table(fno_df, price_df, start_date, end_date)

if master_table.empty:
    st.warning("No data available for the selected date range.")
    st.stop()

filtered_table = apply_filters(master_table, filters, logic=logic)

st.subheader(f"Master Table ({len(filtered_table)} of {len(master_table)} stocks shown)")

# ---- Build the final 9-column display table, in the locked order ----
display_table = filtered_table.copy()

# Flag low-presence stocks: present less than 30% of total days in range.
# Their Change/Range numbers are based on too few data points to be fully reliable.
LOW_PRESENCE_THRESHOLD = 0.30
display_table["_low_presence"] = (
    display_table["Days_Present"] / display_table["Total_Days_In_Range"] < LOW_PRESENCE_THRESHOLD
)

display_table["Days Present"] = (
    display_table["Days_Present"].astype(str) + "/" + display_table["Total_Days_In_Range"].astype(str)
)

display_table = display_table.rename(columns={
    "Price_Pct_Change": "Price% Change",
    "Price_Range_Pct": "Price% Range",
    "Sum_Pct_Change": "Sum% Change",
    "Sum_Pct_End": "Sum% Current",
    "Sum_Pct_Range": "Sum% Range",
    "Clients_Change": "Clients Change",
    "Clients_Range": "Clients Range",
})

final_columns = [
    "Stock", "Price% Change", "Price% Range", "Sum% Current",
    "Sum% Change", "Sum% Range", "Clients Change", "Clients Range", "Days Present"
]
display_table_final = display_table[final_columns + ["_low_presence"]]

# Columns that carry a +/- signed Range value (positive = trended up, negative = trended down)
SIGNED_RANGE_COLUMNS = ["Price% Range", "Sum% Range"]

# All numeric columns get formatted to exactly 1 decimal place
NUMERIC_COLUMNS = [
    "Price% Change", "Price% Range", "Sum% Current",
    "Sum% Change", "Sum% Range", "Clients Change", "Clients Range"
]


def grey_out_low_presence(row):
    """Greys out the entire row's text if the stock has low day-presence in this range."""
    is_low = low_presence_flags.loc[row.name]
    if is_low:
        return ["color: gray"] * len(row)
    return [""] * len(row)


def color_signed_range(val):
    """Conditional formatting for signed Range columns: green if positive, red if negative."""
    if pd.isna(val):
        return ""
    if val > 0:
        return "color: #1D9E75; font-weight: 600"
    if val < 0:
        return "color: #D85A30; font-weight: 600"
    return ""


low_presence_flags = display_table_final["_low_presence"]
styled_table = (
    display_table_final[final_columns]
    .style
    .apply(grey_out_low_presence, axis=1)
    .map(color_signed_range, subset=SIGNED_RANGE_COLUMNS)   # changed from .applymap
    .format({col: "{:.1f}" for col in NUMERIC_COLUMNS}, na_rep="N/A")
    .set_properties(**{"text-align": "center"})
    .set_table_styles([{"selector": "th", "props": [("text-align", "center")]}])
)

st.dataframe(styled_table, width="stretch", hide_index=True)

st.caption(
    "Tip: click any column header in the table to sort by that column. "
    f"Greyed-out rows are present on less than {int(LOW_PRESENCE_THRESHOLD*100)}% of days in the selected range "
    "— treat their Change/Range figures with caution."
)

# ============================================================
# Layer 2 — Stock Drilldown
# ============================================================
st.divider()
st.subheader("Stock Drilldown")

compare_mode = st.toggle("Select Multiple Stocks (Compare Mode)")

all_stock_names = sorted(fno_df["Stock"].unique())

# A consistent color sequence for up to 4 stocks in compare mode
COMPARE_COLORS = ["#7F77DD", "#1D9E75", "#D85A30", "#D4537E"]

if not compare_mode:
    # ---------------- SINGLE STOCK DRILLDOWN ----------------
    selected_stock = st.selectbox(
        "Select a stock to view its detailed trend",
        options=all_stock_names,
        index=None,
        placeholder="Choose a stock..."
    )

    if selected_stock:
        st.markdown(f"### {selected_stock}")

        drill_col1, drill_col2 = st.columns(2)
        with drill_col1:
            drill_start = st.date_input(
                "Start Date", value=overall_min_date,
                min_value=overall_min_date, max_value=overall_max_date,
                format="DD/MM/YYYY", key="drill_start"
            )
        with drill_col2:
            drill_end = st.date_input(
                "End Date", value=overall_max_date,
                min_value=overall_min_date, max_value=overall_max_date,
                format="DD/MM/YYYY", key="drill_end"
            )

        if drill_start > drill_end:
            st.error("Start Date must be before End Date.")
            st.stop()

        ts_data = get_stock_timeseries(fno_df, price_df, selected_stock, drill_start, drill_end)

        chart_col1, chart_col2, chart_col3 = st.columns(3)

        with chart_col1:
            st.markdown("**Stock Price**")
            if not ts_data["price"].empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ts_data["price"]["Date"], y=ts_data["price"]["Close"],
                    mode="lines", line=dict(shape="spline", smoothing=0.6, color="#7F77DD")
                ))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No price data for this range.")

        with chart_col2:
            st.markdown("**Sum %**")
            if not ts_data["sum_pct"].empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ts_data["sum_pct"]["Date"], y=ts_data["sum_pct"]["Sum_Pct"],
                    mode="lines", line=dict(shape="spline", smoothing=0.6, color="#1D9E75")
                ))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No Sum % data for this range.")

        with chart_col3:
            st.markdown("**No. of Clients**")
            if not ts_data["clients"].empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=ts_data["clients"]["Date"], y=ts_data["clients"]["Num_Clients"],
                    mode="lines", line=dict(shape="spline", smoothing=0.6, color="#D85A30")
                ))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No client data for this range.")

else:
    # ---------------- LAYER 3 — COMPARE MODE ----------------
    selected_stocks = st.multiselect(
        "Select up to 4 stocks to compare",
        options=all_stock_names,
        max_selections=4,
        placeholder="Choose stocks..."
    )

    if selected_stocks:
        st.markdown(f"### Comparing: {', '.join(selected_stocks)}")

        cmp_col1, cmp_col2 = st.columns(2)
        with cmp_col1:
            cmp_start = st.date_input(
                "Start Date", value=overall_min_date,
                min_value=overall_min_date, max_value=overall_max_date,
                format="DD/MM/YYYY", key="cmp_start"
            )
        with cmp_col2:
            cmp_end = st.date_input(
                "End Date", value=overall_max_date,
                min_value=overall_min_date, max_value=overall_max_date,
                format="DD/MM/YYYY", key="cmp_end"
            )

        if cmp_start > cmp_end:
            st.error("Start Date must be before End Date.")
            st.stop()

        multi_ts = get_multi_stock_timeseries(fno_df, price_df, selected_stocks, cmp_start, cmp_end)

        chart_col1, chart_col2, chart_col3 = st.columns(3)

        with chart_col1:
            st.markdown("**Stock Price**")
            if not multi_ts["price"].empty:
                fig = go.Figure()
                for i, stock in enumerate(selected_stocks):
                    stock_data = multi_ts["price"][multi_ts["price"]["Stock"] == stock]
                    fig.add_trace(go.Scatter(
                        x=stock_data["Date"], y=stock_data["Close"],
                        mode="lines", name=stock,
                        line=dict(shape="spline", smoothing=0.6, color=COMPARE_COLORS[i % 4])
                    ))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02))
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No price data for this range.")

        with chart_col2:
            st.markdown("**Sum %**")
            if not multi_ts["sum_pct"].empty:
                fig = go.Figure()
                for i, stock in enumerate(selected_stocks):
                    stock_data = multi_ts["sum_pct"][multi_ts["sum_pct"]["Stock"] == stock]
                    fig.add_trace(go.Scatter(
                        x=stock_data["Date"], y=stock_data["Sum_Pct"],
                        mode="lines", name=stock,
                        line=dict(shape="spline", smoothing=0.6, color=COMPARE_COLORS[i % 4])
                    ))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02))
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No Sum % data for this range.")

        with chart_col3:
            st.markdown("**No. of Clients**")
            if not multi_ts["clients"].empty:
                fig = go.Figure()
                for i, stock in enumerate(selected_stocks):
                    stock_data = multi_ts["clients"][multi_ts["clients"]["Stock"] == stock]
                    fig.add_trace(go.Scatter(
                        x=stock_data["Date"], y=stock_data["Num_Clients"],
                        mode="lines", name=stock,
                        line=dict(shape="spline", smoothing=0.6, color=COMPARE_COLORS[i % 4])
                    ))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02))
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("No client data for this range.")

