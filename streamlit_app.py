import hashlib
import io
import os
import sqlite3
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

APP_TITLE = "Trade Journal"
DB_PATH = Path(os.environ.get("TRADE_JOURNAL_DB", "trade_journal_streamlit.db"))

st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon="📈")


# -----------------------------
# Database
# -----------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            broker TEXT,
            symbol TEXT,
            trade_datetime TEXT,
            quantity REAL DEFAULT 0,
            side TEXT,
            trade_price REAL DEFAULT 0,
            buy_price REAL DEFAULT 0,
            sell_price REAL DEFAULT 0,
            proceeds REAL DEFAULT 0,
            commission REAL DEFAULT 0,
            basis REAL DEFAULT 0,
            realized_pl REAL DEFAULT 0,
            notes TEXT,
            import_file TEXT,
            trade_key TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS imported_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT UNIQUE,
            file_name TEXT,
            inserted_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


# -----------------------------
# Helpers
# -----------------------------
def to_float(value, default=0.0):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    text = str(value).replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
    if text == "":
        return default
    try:
        return float(text)
    except ValueError:
        return default


def clean_col(name):
    return str(name or "").strip().lower().replace(" ", "_").replace("-", "_")


def first(row, candidates, default=""):
    for c in candidates:
        if c in row and pd.notna(row[c]) and str(row[c]).strip() != "":
            return row[c]
    return default


def parse_date(value):
    if value is None or str(value).strip() == "":
        return None
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        return None
    return dt.to_pydatetime().replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")


def detect_platform(df):
    cols = {clean_col(c) for c in df.columns}
    joined = " ".join(sorted(cols))
    if "wealthsimple" in joined or {"account", "activity_type", "symbol"}.issubset(cols):
        return "Wealthsimple"
    if "ninjatrader" in joined or {"entry_price", "exit_price"}.issubset(cols) or {"instrument", "profit"}.issubset(cols):
        return "NinjaTrader"
    if "ibkr" in joined or "ib_exec_id" in joined or "fifo_pnl_realized" in joined:
        return "IBKR"
    return "Unknown"


def derive_side(qty, raw_side=""):
    side = str(raw_side or "").upper()
    if side in {"BUY", "BOT", "B", "BOUGHT"}:
        return "BUY"
    if side in {"SELL", "SLD", "S", "SOLD"}:
        return "SELL"
    return "BUY" if qty >= 0 else "SELL"


def make_trade_key(t):
    parts = [
        t.get("platform", ""), t.get("broker", ""), t.get("symbol", ""),
        t.get("trade_datetime", ""), str(round(float(t.get("quantity") or 0), 8)),
        t.get("side", ""), str(round(float(t.get("buy_price") or 0), 8)),
        str(round(float(t.get("sell_price") or 0), 8)),
        str(round(float(t.get("realized_pl") or 0), 8)),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def parse_trade_csv(uploaded_file):
    raw = uploaded_file.getvalue()
    file_hash = hashlib.sha256(raw).hexdigest()
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [clean_col(c) for c in df.columns]
    platform = detect_platform(df)
    trades = []

    for _, row in df.iterrows():
        r = row.to_dict()
        symbol = str(first(r, ["symbol", "ticker", "instrument", "underlying", "description"], "")).strip()
        if not symbol:
            continue

        dt = parse_date(first(r, [
            "trade_date", "fill_date", "execution_date", "executed_at", "transaction_date",
            "date", "datetime", "time", "entry_time"
        ]))

        qty = to_float(first(r, ["quantity", "qty", "shares", "contracts"], 0))
        side = derive_side(qty, first(r, ["side", "buy_sell", "action", "type"], ""))

        buy_price = to_float(first(r, ["buy_price", "buyprice", "entry_price", "entryprice"], 0))
        sell_price = to_float(first(r, ["sell_price", "sellprice", "exit_price", "exitprice", "close_price"], 0))
        trade_price = to_float(first(r, ["trade_price", "price", "avg_price", "average_price"], 0))

        if buy_price == 0 and sell_price == 0 and trade_price:
            if side == "BUY":
                buy_price = trade_price
            else:
                sell_price = trade_price

        realized_pl = to_float(first(r, [
            "realized_pl", "realized_p_l", "p_l", "pl", "profit", "profit_loss",
            "fifo_pnl_realized", "net_p_l", "net_pl"
        ], 0))
        proceeds = to_float(first(r, ["proceeds", "amount", "net_amount", "net_cash", "cash"], 0))
        commission = to_float(first(r, ["commission", "fees", "ib_commission"], 0))
        basis = to_float(first(r, ["basis", "cost_basis", "cost"], 0))

        broker = str(first(r, ["broker", "source"], platform)).strip() or platform
        t = {
            "platform": platform,
            "broker": broker,
            "symbol": symbol,
            "trade_datetime": dt,
            "quantity": qty,
            "side": side,
            "trade_price": trade_price,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "proceeds": proceeds,
            "commission": commission,
            "basis": basis,
            "realized_pl": realized_pl,
            "notes": "Imported from CSV",
            "import_file": uploaded_file.name,
        }
        t["trade_key"] = make_trade_key(t)
        trades.append(t)

    return file_hash, platform, trades


def insert_trades(trades, file_hash, file_name):
    conn = get_conn()
    existing_file = conn.execute("SELECT id FROM imported_files WHERE file_hash = ?", (file_hash,)).fetchone()
    inserted = 0
    skipped = 0
    for t in trades:
        try:
            conn.execute(
                """
                INSERT INTO trades (
                    platform, broker, symbol, trade_datetime, quantity, side, trade_price,
                    buy_price, sell_price, proceeds, commission, basis, realized_pl, notes,
                    import_file, trade_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    t["platform"], t["broker"], t["symbol"], t["trade_datetime"], t["quantity"],
                    t["side"], t["trade_price"], t["buy_price"], t["sell_price"], t["proceeds"],
                    t["commission"], t["basis"], t["realized_pl"], t["notes"], t["import_file"],
                    t["trade_key"],
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.execute(
        "INSERT OR IGNORE INTO imported_files (file_hash, file_name, inserted_count, skipped_count) VALUES (?, ?, ?, ?)",
        (file_hash, file_name, inserted, skipped),
    )
    conn.commit()
    conn.close()
    return inserted, skipped, bool(existing_file)


def load_trades():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY COALESCE(trade_datetime, created_at) DESC, id DESC", conn)
    conn.close()
    return df


def monthly_platform_calendar(df):
    if df.empty or "trade_datetime" not in df:
        return pd.DataFrame()
    x = df.copy()
    x["date"] = pd.to_datetime(x["trade_datetime"], errors="coerce").dt.date
    x = x.dropna(subset=["date"])
    if x.empty:
        return pd.DataFrame()
    x["month"] = pd.to_datetime(x["date"]).dt.to_period("M").astype(str)
    return x.groupby(["month", "platform"], as_index=False).agg(realized_pl=("realized_pl", "sum"), trades=("id", "count"))


# -----------------------------
# UI
# -----------------------------
init_db()

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; }
    [data-testid="stMetricValue"] { font-size: 1.6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 Trade Journal — Streamlit")
st.caption("Deployable starter version. Upload your latest Flask app/project for a full 1:1 migration.")

with st.sidebar:
    st.header("Navigation")
    page = st.radio("Page", ["Dashboard", "Import CSV", "Trades", "Export"], label_visibility="collapsed")
    st.divider()
    st.info("SQLite is okay for local testing. Use PostgreSQL/Supabase for production deployment.")

trades_df = load_trades()

if page == "Import CSV":
    st.header("📤 Import Trade CSV")
    uploaded = st.file_uploader("Upload IBKR / NinjaTrader / Wealthsimple CSV", type=["csv"])
    if uploaded:
        try:
            file_hash, platform, trades = parse_trade_csv(uploaded)
            st.write(f"Detected platform: **{platform}**")
            st.write(f"Parsed rows: **{len(trades)}**")
            if st.button("Import trades", type="primary"):
                inserted, skipped, seen_before = insert_trades(trades, file_hash, uploaded.name)
                st.success(f"Inserted {inserted}, skipped {skipped}.")
                if seen_before:
                    st.warning("This file hash was imported before; duplicate trade protection was applied.")
                st.rerun()
            if trades:
                st.dataframe(pd.DataFrame(trades), use_container_width=True)
        except Exception as e:
            st.error(str(e))

elif page == "Trades":
    st.header("📋 Trades")
    if trades_df.empty:
        st.info("No trades yet.")
    else:
        show_cols = [c for c in ["platform", "broker", "symbol", "trade_datetime", "quantity", "side", "buy_price", "sell_price", "realized_pl", "notes"] if c in trades_df]
        st.dataframe(trades_df[show_cols], use_container_width=True, hide_index=True)

elif page == "Export":
    st.header("⬇️ Export")
    if trades_df.empty:
        st.info("No trades to export.")
    else:
        csv = trades_df.to_csv(index=False).encode("utf-8")
        st.download_button("Download trades CSV", csv, "trades_export.csv", "text/csv")

else:
    st.header("Dashboard")
    if trades_df.empty:
        st.info("Upload CSV files to start building your dashboard.")
    else:
        total_pnl = float(trades_df["realized_pl"].fillna(0).sum())
        trade_count = int(len(trades_df))
        wins = trades_df[trades_df["realized_pl"].fillna(0) > 0]
        win_rate = (len(wins) / trade_count * 100) if trade_count else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total P&L", f"{total_pnl:,.2f}")
        c2.metric("Trades", f"{trade_count}")
        c3.metric("Win Rate", f"{win_rate:.1f}%")
        c4.metric("Platforms", trades_df["platform"].nunique())

        st.subheader("Platform P&L")
        platform = trades_df.groupby("platform", as_index=False)["realized_pl"].sum()
        st.plotly_chart(px.bar(platform, x="platform", y="realized_pl", text_auto=".2f"), use_container_width=True)

        st.subheader("Monthly P&L by Platform")
        monthly = monthly_platform_calendar(trades_df)
        if not monthly.empty:
            st.plotly_chart(px.bar(monthly, x="month", y="realized_pl", color="platform", barmode="group"), use_container_width=True)
            st.dataframe(monthly, use_container_width=True, hide_index=True)

        st.subheader("Recent Trades")
        show_cols = [c for c in ["platform", "symbol", "trade_datetime", "side", "buy_price", "sell_price", "realized_pl"] if c in trades_df]
        st.dataframe(trades_df[show_cols].head(50), use_container_width=True, hide_index=True)
