import calendar
import hashlib
import importlib.util
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dropbox_import import download_new_csvs

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "trades_streamlit.db"
UPLOAD_DIR = APP_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Reuse your Flask app's battle-tested broker parsers without running Flask.
spec = importlib.util.spec_from_file_location("legacy_flask_app", APP_DIR / "legacy_flask_app.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)

st.set_page_config(page_title="Trade Journal", page_icon="📈", layout="wide")

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
  --bg:#0c0f14;
  --sidebar:#11151c;
  --panel:#151a22;
  --panel-soft:#10141b;
  --text:#eef2f7;
  --muted:#9aa4b2;
  --border:#252c37;
  --green:#4ade80;
  --red:#fb7185;
  --yellow:#fbbf24;
  --accent:#8b5cf6;
}
html, body, [data-testid="stAppViewContainer"] {
  background: radial-gradient(circle at top left, rgba(139,92,246,.10), transparent 32%), var(--bg)!important;
  color:var(--text)!important;
}
* { font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
.block-container { max-width:1280px; padding:1.25rem 1.4rem 2.5rem 1.4rem; }
#MainMenu, footer, header { visibility:hidden; }
[data-testid="stSidebar"] { background:var(--sidebar)!important; border-right:1px solid var(--border)!important; }
[data-testid="stSidebar"] * { color:var(--text)!important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color:var(--muted)!important; }
.sidebar-brand { margin:4px 0 18px; }
.sidebar-title { font-size:18px; font-weight:700; letter-spacing:-.03em; color:var(--text)!important; }
.sidebar-sub { color:var(--muted); font-size:12px; margin-top:3px; }
.portfolio-chip { background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:11px 12px; margin:10px 0 14px; }
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] div[data-baseweb="select"] > div { background:var(--panel)!important; border:1px solid var(--border)!important; border-radius:10px!important; color:var(--text)!important; }
[data-testid="stSidebar"] [role="radiogroup"] label { border-radius:9px!important; padding:8px 9px!important; margin:1px 0!important; border:1px solid transparent; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background:#1b222d!important; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background:var(--panel)!important; border-color:#3a4352!important; }
.page-title { font-size:28px; font-weight:700; letter-spacing:-.04em; margin:4px 0 4px; color:var(--text)!important; }
.page-subtitle { color:var(--muted); font-size:14px; margin-bottom:18px; }
.hero-pill { background:var(--panel); border:1px solid var(--border); padding:8px 11px; border-radius:10px; color:var(--muted); font-size:13px; white-space:nowrap; }
.dj-card, div[data-testid="stMetric"], [data-testid="stDataFrame"] { background:rgba(21,26,34,.96); border:1px solid var(--border); border-radius:14px; padding:15px; box-shadow:none; }
.dj-card-sm { min-height:92px; }
.dj-label { color:var(--muted); font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; margin-bottom:6px; }
.dj-value { font-size:24px; font-weight:700; letter-spacing:-.03em; color:var(--text); }
.dj-sub, .muted { color:var(--muted); font-size:13px; }
.section-title { font-size:18px; font-weight:700; letter-spacing:-.03em; margin:8px 0 10px; color:var(--text); }
.pos { color:var(--green)!important; } .neg { color:var(--red)!important; } .yellow { color:var(--yellow)!important; }
.calendar-cell { border:1px solid var(--border); border-radius:12px; padding:8px; min-height:78px; overflow:hidden; background:#111720; }
.calendar-day { font-weight:700; color:var(--text); } .calendar-pnl { font-weight:700; font-size:13px; } .small-platform { font-size:10px; line-height:1.15; opacity:.9; }
[data-testid="stExpander"] { background:var(--panel); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
[data-testid="stExpander"] summary { color:var(--text)!important; font-weight:700; }
[data-testid="stDataFrame"] { padding:0!important; overflow:hidden; }
.stButton > button, .stDownloadButton > button { border-radius:10px!important; border:1px solid #374151!important; background:#f3f4f6!important; color:#111827!important; font-weight:650!important; min-height:38px; box-shadow:none!important; }
.stButton > button:hover, .stDownloadButton > button:hover { background:#ffffff!important; border-color:#ffffff!important; }
div[data-baseweb="select"] > div, input, textarea { border-radius:10px!important; background:var(--panel)!important; border-color:var(--border)!important; color:var(--text)!important; box-shadow:none!important; }
[data-testid="stFileUploader"] { background:var(--panel); border:1px dashed #3b4350; border-radius:14px; padding:14px; }
[data-testid="stFileUploader"] * { color:var(--text)!important; }
[data-testid="stDataFrame"] iframe, .stDataFrame { background:var(--panel)!important; }
hr { border-color:var(--border)!important; }
/* Streamlit native alerts/cards */
[data-testid="stAlert"] { background:var(--panel)!important; border:1px solid var(--border)!important; color:var(--text)!important; }
@media (max-width:800px) { .page-title{font-size:24px;} .block-container{padding:1rem;} }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            portfolio_id INTEGER NOT NULL,
            broker TEXT NOT NULL,
            asset_category TEXT,
            currency TEXT,
            symbol TEXT NOT NULL,
            trade_datetime TEXT,
            quantity REAL,
            side TEXT,
            trade_price REAL,
            close_price REAL,
            buy_price REAL,
            sell_price REAL,
            proceeds REAL,
            commission REAL,
            basis REAL,
            realized_pl REAL,
            mtm_pl REAL,
            risk_amount REAL,
            r_multiple REAL,
            code TEXT,
            import_file TEXT,
            batch_id TEXT,
            notes TEXT,
            trade_key TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trade_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER NOT NULL UNIQUE,
            setup_tag TEXT,
            mistake_tag TEXT,
            note TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS imported_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            file_name TEXT,
            file_hash TEXT NOT NULL,
            batch_id TEXT,
            parsed_count INTEGER DEFAULT 0,
            inserted_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            status TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, source, file_hash)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_scope ON trades(user_id, portfolio_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trade_key ON trades(user_id, portfolio_id, trade_key)")
    conn.commit()
    conn.close()


def get_or_create_user(email="streamlit@local"):
    conn = connect()
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if row:
        uid = row["id"]
    else:
        cur = conn.execute("INSERT INTO users(email) VALUES (?)", (email,))
        uid = cur.lastrowid
        conn.commit()
    conn.close()
    return uid


def get_portfolios(user_id):
    conn = connect()
    rows = conn.execute("SELECT id, name FROM portfolios WHERE user_id = ? ORDER BY name", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_or_create_portfolio(user_id, name="Main Portfolio"):
    conn = connect()
    row = conn.execute("SELECT id FROM portfolios WHERE user_id = ? AND name = ?", (user_id, name)).fetchone()
    if row:
        pid = row["id"]
    else:
        cur = conn.execute("INSERT OR IGNORE INTO portfolios(user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
        row = conn.execute("SELECT id FROM portfolios WHERE user_id = ? AND name = ?", (user_id, name)).fetchone()
        pid = row["id"]
    conn.close()
    return pid


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def to_float(v, default=0.0):
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(v)
    except Exception:
        return default


def normalize_key_value(value, places=8):
    if value is None:
        return ""
    text = str(value).strip()
    if text == "":
        return ""
    try:
        return f"{float(text):.{places}f}"
    except Exception:
        return text.upper()


def make_trade_key(user_id, portfolio_id, trade):
    if hasattr(legacy, "make_trade_key"):
        try:
            return legacy.make_trade_key(user_id, portfolio_id, trade)
        except Exception:
            pass
    parts = [
        str(user_id), str(portfolio_id),
        str(trade.get("broker") or "").upper().strip(),
        str(trade.get("symbol") or "").upper().strip(),
        str(trade.get("trade_datetime") or "").strip(),
        normalize_key_value(trade.get("quantity")),
        str(trade.get("side") or "").upper().strip(),
        normalize_key_value(trade.get("trade_price")),
        normalize_key_value(trade.get("proceeds")),
        normalize_key_value(trade.get("commission")),
        str(trade.get("code") or "").upper().strip(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def derive_buy_sell_prices(trade):
    if hasattr(legacy, "derive_buy_sell_prices"):
        try:
            return legacy.derive_buy_sell_prices(trade)
        except Exception:
            pass
    buy = to_float(trade.get("buy_price"))
    sell = to_float(trade.get("sell_price"))
    if buy or sell:
        return buy, sell
    side = str(trade.get("side") or "").upper()
    qty = to_float(trade.get("quantity"))
    trade_price = to_float(trade.get("trade_price"))
    close_price = to_float(trade.get("close_price"))
    if side == "BUY" or qty > 0:
        return trade_price, close_price
    if side == "SELL" or qty < 0:
        return close_price, trade_price
    return 0.0, 0.0


def load_existing_wealthsimple_trades(user_id, portfolio_id):
    conn = connect()
    rows = conn.execute("""
        SELECT * FROM trades
        WHERE user_id = ? AND portfolio_id = ? AND LOWER(broker) LIKE '%wealthsimple%'
        ORDER BY COALESCE(trade_datetime, ''), id
    """, (user_id, portfolio_id)).fetchall()
    conn.close()
    existing = []
    for r in rows:
        d = dict(r)
        d["db_id"] = d.get("id")
        d["is_new"] = False
        existing.append(d)
    return existing


def recompute_wealthsimple_fifo_for_streamlit(existing_trades, new_trades):
    """Compute Wealthsimple realized P&L from buys/sells using FIFO.

    Wealthsimple activity CSVs often do not include a realized P&L column.
    This fills realized_pl on SELL rows, sets basis, and keeps BUY rows at 0 P&L.
    Existing Wealthsimple rows are included so re-importing later sells can match
    older buy lots already in the database.
    """
    combined = []
    for t in existing_trades:
        item = dict(t)
        item["is_new"] = False
        combined.append(item)
    for t in new_trades:
        item = dict(t)
        item["is_new"] = True
        item["db_id"] = None
        combined.append(item)

    groups = {}
    for t in combined:
        key = (str(t.get("symbol") or "").upper().strip(), str(t.get("currency") or "CAD").upper().strip())
        groups.setdefault(key, []).append(t)

    updates = []
    for _, items in groups.items():
        items.sort(key=lambda x: (str(x.get("trade_datetime") or ""), 0 if to_float(x.get("quantity")) > 0 else 1, int(x.get("db_id") or 0)))
        lots = []

        for trade in items:
            qty = to_float(trade.get("quantity"))
            price = to_float(trade.get("trade_price"))
            commission = to_float(trade.get("commission"))

            if qty > 0:
                total_cost = qty * price + commission
                unit_cost = total_cost / qty if qty else 0.0
                lots.append({"qty_remaining": qty, "unit_cost": unit_cost})
                trade["basis"] = round(total_cost, 2)
                trade["realized_pl"] = 0.0

            elif qty < 0:
                sell_qty = abs(qty)
                gross_sale = sell_qty * price
                net_sale = gross_sale - commission
                remaining = sell_qty
                total_basis = 0.0

                while remaining > 1e-12 and lots:
                    lot = lots[0]
                    matched = min(remaining, lot["qty_remaining"])
                    total_basis += matched * lot["unit_cost"]
                    lot["qty_remaining"] -= matched
                    remaining -= matched
                    if lot["qty_remaining"] <= 1e-12:
                        lots.pop(0)

                trade["basis"] = round(total_basis, 2)
                trade["realized_pl"] = round(net_sale - total_basis, 2)

            trade["mtm_pl"] = trade.get("realized_pl", 0.0)

            if not trade.get("is_new") and trade.get("db_id"):
                updates.append({
                    "db_id": trade["db_id"],
                    "basis": to_float(trade.get("basis")),
                    "realized_pl": to_float(trade.get("realized_pl")),
                    "mtm_pl": to_float(trade.get("mtm_pl")),
                })

    return updates, [t for t in combined if t.get("is_new")]


def update_existing_wealthsimple_fifo_values(updates):
    if not updates:
        return
    conn = connect()
    for u in updates:
        conn.execute(
            "UPDATE trades SET basis = ?, realized_pl = ?, mtm_pl = ? WHERE id = ?",
            (u["basis"], u["realized_pl"], u["mtm_pl"], u["db_id"]),
        )
    conn.commit()
    conn.close()


def prepare_trades_for_import(user_id, portfolio_id, import_type, trades):
    if import_type == "wealthsimple":
        existing = load_existing_wealthsimple_trades(user_id, portfolio_id)
        updates, prepared = recompute_wealthsimple_fifo_for_streamlit(existing, trades)
        update_existing_wealthsimple_fifo_values(updates)
        return prepared
    return trades


def parse_money_value(value):
    text = str(value or "").strip()
    if text == "":
        return 0.0
    negative = text.startswith("(") or "$(" in text or text.startswith("-")
    text = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "").strip()
    try:
        number = float(text)
    except ValueError:
        return 0.0
    return -abs(number) if negative else number


def parse_dt_streamlit(raw):
    raw = str(raw or "").strip()
    if not raw:
        return None
    for fmt in (
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(raw, errors="coerce").to_pydatetime()
    except Exception:
        return None


def is_ninjatrader_performance_csv(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            header = f.readline().strip().lower()
        required = ["symbol", "buyprice", "sellprice", "pnl", "boughttimestamp", "soldtimestamp"]
        compact = header.replace("_", "").replace(" ", "")
        return all(item in compact for item in required)
    except Exception:
        return False


def parse_ninjatrader_performance_csv(path):
    """Parse NinjaTrader Performance CSV closed trades.

    Supports headers like:
    symbol, buyFillId, sellFillId, qty, buyPrice, sellPrice, pnl,
    boughtTimestamp, soldTimestamp, duration

    Trade date is the entry timestamp: buy time for long trades, sell time for short trades.
    This keeps the calendar aligned with when the trade was opened.
    """
    df = pd.read_csv(path, encoding="utf-8-sig")
    normalized = {str(c).strip().lower().replace("_", "").replace(" ", ""): c for c in df.columns}

    def get_col(*names):
        for name in names:
            key = name.lower().replace("_", "").replace(" ", "")
            if key in normalized:
                return normalized[key]
        return None

    symbol_col = get_col("symbol")
    qty_col = get_col("qty", "quantity")
    buy_price_col = get_col("buyPrice", "buy price")
    sell_price_col = get_col("sellPrice", "sell price")
    pnl_col = get_col("pnl", "P&L", "profit")
    bought_col = get_col("boughtTimestamp", "bought timestamp", "buyTime", "buy time")
    sold_col = get_col("soldTimestamp", "sold timestamp", "sellTime", "sell time")
    buy_id_col = get_col("buyFillId", "buy fill id")
    sell_id_col = get_col("sellFillId", "sell fill id")
    duration_col = get_col("duration")

    missing = [name for name, col in {
        "symbol": symbol_col,
        "qty": qty_col,
        "buyPrice": buy_price_col,
        "sellPrice": sell_price_col,
        "pnl": pnl_col,
        "boughtTimestamp": bought_col,
        "soldTimestamp": sold_col,
    }.items() if col is None]
    if missing:
        raise ValueError(f"NinjaTrader CSV missing required columns: {', '.join(missing)}")

    trades = []
    for _, row in df.iterrows():
        symbol = str(row.get(symbol_col, "") or "").strip()
        if not symbol:
            continue

        qty = abs(parse_money_value(row.get(qty_col, 0)))
        buy_price = parse_money_value(row.get(buy_price_col, 0))
        sell_price = parse_money_value(row.get(sell_price_col, 0))
        realized_pl = parse_money_value(row.get(pnl_col, 0))
        bought_dt = parse_dt_streamlit(row.get(bought_col, ""))
        sold_dt = parse_dt_streamlit(row.get(sold_col, ""))

        is_long = True
        if bought_dt and sold_dt:
            is_long = bought_dt <= sold_dt

        entry_dt = bought_dt if is_long else sold_dt
        exit_dt = sold_dt if is_long else bought_dt
        trade_dt = entry_dt or exit_dt
        side = "BUY" if is_long else "SELL"
        signed_qty = qty if is_long else -qty
        entry_price = buy_price if is_long else sell_price
        close_price = sell_price if is_long else buy_price
        buy_id = str(row.get(buy_id_col, "") if buy_id_col else "").strip()
        sell_id = str(row.get(sell_id_col, "") if sell_id_col else "").strip()
        duration = str(row.get(duration_col, "") if duration_col else "").strip()

        trades.append({
            "broker": "NinjaTrader Performance",
            "asset_category": "FUT",
            "currency": "USD",
            "symbol": symbol,
            "trade_datetime": trade_dt.isoformat() if trade_dt else None,
            "quantity": signed_qty,
            "side": side,
            "trade_price": entry_price,
            "close_price": close_price,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "proceeds": realized_pl,
            "commission": 0.0,
            "basis": 0.0,
            "realized_pl": realized_pl,
            "mtm_pl": 0.0,
            "code": f"NINJATRADER:{buy_id}:{sell_id}",
            "notes": f"Entry: {entry_dt}; Exit: {exit_dt}; Duration: {duration}",
            "risk_amount": 0.0,
            "r_multiple": 0.0,
        })
    return trades


def parse_uploaded_file(path):
    # Handle NinjaTrader Performance CSV directly here so this exact export format
    # imports reliably and shows every closed trade on the calendar/details table.
    if is_ninjatrader_performance_csv(path):
        return "performance", parse_ninjatrader_performance_csv(path)

    import_type = legacy.detect_import_type(str(path))
    if import_type in {"ibkr", "ibkr_trades"}:
        return import_type, legacy.parse_ibkr_activity_csv(str(path))
    if import_type == "ibkr_summary":
        return import_type, legacy.parse_ibkr_summary_csv(str(path))
    if import_type == "wealthsimple":
        return import_type, legacy.parse_wealthsimple_csv(str(path))
    if import_type == "performance":
        return import_type, parse_ninjatrader_performance_csv(path)
    raise ValueError(f"Unsupported or unrecognized CSV format: {import_type}")


def insert_trades(user_id, portfolio_id, trades, import_file=None, batch_id=None):
    conn = connect()
    cur = conn.cursor()
    inserted = 0
    skipped = 0
    seen = set()
    for t in trades:
        t = dict(t)
        t.setdefault("broker", "Unknown")
        t.setdefault("asset_category", "")
        t.setdefault("currency", "")
        t.setdefault("symbol", "Unknown")
        t.setdefault("trade_datetime", None)
        t.setdefault("quantity", 0)
        t.setdefault("side", "")
        t.setdefault("trade_price", 0)
        t.setdefault("close_price", 0)
        t.setdefault("proceeds", 0)
        t.setdefault("commission", 0)
        t.setdefault("basis", 0)
        t.setdefault("realized_pl", 0)
        t.setdefault("mtm_pl", 0)
        t.setdefault("risk_amount", 0)
        t.setdefault("r_multiple", 0)
        t.setdefault("code", "")
        t.setdefault("notes", "")
        buy_price, sell_price = derive_buy_sell_prices(t)
        t["buy_price"] = buy_price
        t["sell_price"] = sell_price
        key = make_trade_key(user_id, portfolio_id, t)
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        existing = cur.execute(
            "SELECT id FROM trades WHERE user_id=? AND portfolio_id=? AND trade_key=? LIMIT 1",
            (user_id, portfolio_id, key),
        ).fetchone()
        if existing:
            skipped += 1
            continue
        cur.execute("""
            INSERT INTO trades (
                user_id, portfolio_id, broker, asset_category, currency, symbol,
                trade_datetime, quantity, side, trade_price, close_price, buy_price, sell_price,
                proceeds, commission, basis, realized_pl, mtm_pl, risk_amount, r_multiple,
                code, import_file, batch_id, notes, trade_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, portfolio_id, t["broker"], t["asset_category"], t["currency"], t["symbol"],
            t["trade_datetime"], to_float(t["quantity"]), t["side"], to_float(t["trade_price"]),
            to_float(t["close_price"]), to_float(t["buy_price"]), to_float(t["sell_price"]),
            to_float(t["proceeds"]), to_float(t["commission"]), to_float(t["basis"]),
            to_float(t["realized_pl"]), to_float(t["mtm_pl"]), to_float(t["risk_amount"]),
            to_float(t["r_multiple"]), t["code"], import_file, batch_id, t["notes"], key,
        ))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted, skipped


def load_trades_df(user_id, portfolio_id):
    conn = connect()
    df = pd.read_sql_query("""
        SELECT t.*, j.setup_tag, j.mistake_tag, j.note AS journal_note
        FROM trades t
        LEFT JOIN trade_journal j ON j.trade_id = t.id
        WHERE t.user_id = ? AND t.portfolio_id = ?
        ORDER BY COALESCE(t.trade_datetime, '') DESC, t.id DESC
    """, conn, params=(user_id, portfolio_id))
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["trade_datetime"], errors="coerce").dt.date
        df["month"] = pd.to_datetime(df["trade_datetime"], errors="coerce").dt.to_period("M").astype(str)
    return df


def broker_platform_name(broker):
    b = str(broker or "").lower()
    if "wealthsimple" in b:
        return "Wealthsimple"
    if "ninja" in b or "performance" in b:
        return "NinjaTrader"
    if "ibkr" in b or "interactive" in b:
        return "IBKR"
    return "Other"


def render_metric(label, value, klass=""):
    st.markdown(
        f'<div class="dj-card dj-card-sm"><div class="dj-label">{label}</div><div class="dj-value {klass}">{value}</div></div>',
        unsafe_allow_html=True,
    )


def stat_card(label, value, subtitle="", icon="↑", tone="red"):
    icon_cls = "dj-icon yellow" if tone == "yellow" else "dj-icon"
    st.markdown(
        f"""
        <div class="dj-card dj-card-sm">
          <div class="metric-row">
            <div class="{icon_cls}">{icon}</div>
            <div>
              <div class="dj-value">{value}</div>
              <div class="dj-sub">{subtitle or label}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def dj_panel(title, body_html):
    st.markdown(f'<div class="dj-card"><div class="section-title">{title}</div>{body_html}</div>', unsafe_allow_html=True)


def top_nav():
    st.markdown(
        """
        <div class="top-nav">
          <div class="top-tabs"><span>Home</span><span>Settings</span><span>Help</span></div>
          <div class="search-pill"><span>Search Reports...</span><span>⌕</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sub_tabs():
    st.markdown(
        '<div class="sub-tabs"><span>Overview</span><span>Account</span><span>Trades</span><span>Analytics</span><span>Reports</span><span>Goals</span></div>',
        unsafe_allow_html=True,
    )


def money(x):
    x = to_float(x)
    sign = "+" if x > 0 else ""
    return f"{sign}{x:,.2f}"


def render_hero(title, subtitle="", portfolio_name=None):
    right = f'<div class="hero-pill">Portfolio: {portfolio_name}</div>' if portfolio_name else ''
    html = f"""
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin:4px 0 14px;">
        <div>
          <div class="page-title">{title}</div>
          <div class="page-subtitle">{subtitle}</div>
        </div>
        {right}
      </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def section_heading(title, subtitle=""):
    html = f'<div class="section-title">{title}</div>'
    if subtitle:
        html += f'<div class="muted">{subtitle}</div>'
    st.markdown(html, unsafe_allow_html=True)


def generate_tomorrow_plan(df):
    if df.empty:
        return {"mode": "Collect data", "best_setup": "No data", "avoid_setup": "No data", "best_time": "No data", "confidence": 0, "reason": "Import trades first."}
    work = df.copy()
    work["setup"] = work.get("setup_tag", pd.Series([None] * len(work))).fillna("Unlabeled")
    work["pnl"] = pd.to_numeric(work["realized_pl"], errors="coerce").fillna(0)
    setup = work.groupby("setup")["pnl"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    best = setup.index[0] if len(setup) else "No data"
    worst = setup.index[-1] if len(setup) else "No data"
    work["dt"] = pd.to_datetime(work["trade_datetime"], errors="coerce")
    work["bucket"] = work["dt"].dt.hour.map(lambda h: "Morning" if pd.notna(h) and h < 11 else "Midday" if pd.notna(h) and h < 14 else "Afternoon" if pd.notna(h) else "Unknown")
    time_edge = work.groupby("bucket")["pnl"].sum().sort_values(ascending=False)
    best_time = time_edge.index[0] if len(time_edge) else "No data"
    recent = work.head(10)["pnl"].sum()
    confidence = min(95, int(abs(recent) / 50) + min(40, int(setup.iloc[0]["count"] * 5)) if len(setup) else 0)
    return {"mode": "Selective", "best_setup": best, "avoid_setup": worst, "best_time": best_time, "confidence": confidence, "reason": f"{best} has the strongest recent/overall P&L in your journal."}



def get_secret_value(*names, default=""):
    """Read a value from Streamlit secrets using a few possible key names."""
    for name in names:
        try:
            if "." in name:
                head, tail = name.split(".", 1)
                value = st.secrets.get(head, {}).get(tail, "")
            else:
                value = st.secrets.get(name, "")
            if value:
                return str(value)
        except Exception:
            continue
    return default


def has_imported_source_hash(user_id, source, file_hash):
    conn = connect()
    row = conn.execute(
        "SELECT id FROM imported_files WHERE user_id=? AND source=? AND file_hash=? LIMIT 1",
        (user_id, source, file_hash),
    ).fetchone()
    conn.close()
    return row is not None


def record_imported_source_file(user_id, source, file_name, file_hash, batch_id, parsed_count, inserted_count, skipped_count, status):
    conn = connect()
    conn.execute(
        """
        INSERT OR IGNORE INTO imported_files(
            user_id, source, file_name, file_hash, batch_id,
            parsed_count, inserted_count, skipped_count, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, source, file_name, file_hash, batch_id, parsed_count, inserted_count, skipped_count, status),
    )
    conn.commit()
    conn.close()


def get_import_batches(user_id, portfolio_id):
    """Return import batches visible to the current user/portfolio.

    Includes normal batches with trades and imported_files rows so stale file-hash
    records can be removed too.
    """
    conn = connect()
    trade_rows = conn.execute(
        """
        SELECT
            batch_id,
            MIN(import_file) AS file_name,
            MIN(broker) AS broker,
            COUNT(*) AS trade_count,
            ROUND(SUM(IFNULL(realized_pl, 0)), 2) AS pnl,
            MIN(substr(trade_datetime, 1, 10)) AS first_trade_date,
            MAX(substr(trade_datetime, 1, 10)) AS last_trade_date
        FROM trades
        WHERE user_id = ?
          AND portfolio_id = ?
          AND batch_id IS NOT NULL
          AND TRIM(batch_id) != ''
        GROUP BY batch_id
        ORDER BY MAX(created_at) DESC, batch_id DESC
        """,
        (user_id, portfolio_id),
    ).fetchall()

    file_rows = conn.execute(
        """
        SELECT
            batch_id, source, file_name, parsed_count, inserted_count,
            skipped_count, status, imported_at
        FROM imported_files
        WHERE user_id = ?
          AND batch_id IS NOT NULL
          AND TRIM(batch_id) != ''
        ORDER BY imported_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()

    batches = {}
    for r in trade_rows:
        d = dict(r)
        batches[d["batch_id"]] = {
            "batch_id": d["batch_id"],
            "source": "trades",
            "file_name": d.get("file_name") or "",
            "broker": d.get("broker") or "",
            "trade_count": int(d.get("trade_count") or 0),
            "pnl": float(d.get("pnl") or 0),
            "first_trade_date": d.get("first_trade_date") or "",
            "last_trade_date": d.get("last_trade_date") or "",
            "parsed_count": None,
            "inserted_count": None,
            "skipped_count": None,
            "status": "",
            "imported_at": "",
        }

    for r in file_rows:
        d = dict(r)
        bid = d["batch_id"]
        item = batches.setdefault(bid, {
            "batch_id": bid,
            "source": d.get("source") or "",
            "file_name": d.get("file_name") or "",
            "broker": "",
            "trade_count": 0,
            "pnl": 0.0,
            "first_trade_date": "",
            "last_trade_date": "",
            "parsed_count": d.get("parsed_count"),
            "inserted_count": d.get("inserted_count"),
            "skipped_count": d.get("skipped_count"),
            "status": d.get("status") or "",
            "imported_at": d.get("imported_at") or "",
        })
        item["source"] = d.get("source") or item.get("source") or ""
        item["file_name"] = d.get("file_name") or item.get("file_name") or ""
        item["parsed_count"] = d.get("parsed_count")
        item["inserted_count"] = d.get("inserted_count")
        item["skipped_count"] = d.get("skipped_count")
        item["status"] = d.get("status") or item.get("status") or ""
        item["imported_at"] = d.get("imported_at") or item.get("imported_at") or ""

    return sorted(batches.values(), key=lambda x: x.get("imported_at") or x.get("batch_id") or "", reverse=True)


def delete_import_batch(user_id, portfolio_id, batch_id):
    """Delete one import batch and its file-hash tracking row.

    This lets you delete an old Wealthsimple/NinjaTrader/IBKR batch and re-import
    the same CSV without the app saying it was already imported.
    """
    if not batch_id:
        return {"trades_deleted": 0, "file_records_deleted": 0}

    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM trades
        WHERE user_id = ? AND portfolio_id = ? AND batch_id = ?
        """,
        (user_id, portfolio_id, batch_id),
    )
    trades_deleted = cur.rowcount

    cur.execute(
        """
        DELETE FROM imported_files
        WHERE user_id = ? AND batch_id = ?
        """,
        (user_id, batch_id),
    )
    file_records_deleted = cur.rowcount
    conn.commit()
    conn.close()
    return {"trades_deleted": trades_deleted, "file_records_deleted": file_records_deleted}


def import_one_csv_path(user_id, portfolio_id, path, source, file_hash_value=None):
    path = Path(path)
    digest = file_hash_value or file_hash(path)
    if has_imported_source_hash(user_id, source, digest):
        return {
            "file": path.name,
            "status": "skipped_file_hash",
            "parsed": 0,
            "inserted": 0,
            "skipped": 0,
            "message": "Skipped already imported file.",
        }

    import_type, trades = parse_uploaded_file(path)
    trades = prepare_trades_for_import(user_id, portfolio_id, import_type, trades)
    batch_id = f"{source.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    inserted, skipped = insert_trades(user_id, portfolio_id, trades, path.name, batch_id)
    record_imported_source_file(
        user_id,
        source,
        path.name,
        digest,
        batch_id,
        len(trades),
        inserted,
        skipped,
        "OK",
    )
    return {
        "file": path.name,
        "status": "imported",
        "type": import_type,
        "batch_id": batch_id,
        "parsed": len(trades),
        "inserted": inserted,
        "skipped": skipped,
        "message": f"{import_type}: parsed {len(trades)}, inserted {inserted}, skipped {skipped}.",
    }


def render_dropbox_import_page(user_id, portfolio_id):
    render_hero("Dropbox", "Cloud-friendly folder import for broker CSV exports.")

    token = get_secret_value("dropbox.access_token", "DROPBOX_ACCESS_TOKEN")
    app_key = get_secret_value("dropbox.app_key", "DROPBOX_APP_KEY")
    app_secret = get_secret_value("dropbox.app_secret", "DROPBOX_APP_SECRET")
    refresh_token = get_secret_value("dropbox.refresh_token", "DROPBOX_REFRESH_TOKEN")
    default_folder = get_secret_value("dropbox.folder", "DROPBOX_FOLDER", default="/TradeJournalExports")
    has_dropbox_auth = bool(refresh_token and app_key and app_secret) or bool(token)

    with st.expander("How to configure Streamlit secrets", expanded=not has_dropbox_auth):
        st.markdown(
            """
Recommended production setup uses a **Dropbox refresh token**:

```toml
[dropbox]
app_key = "YOUR_DROPBOX_APP_KEY"
app_secret = "YOUR_DROPBOX_APP_SECRET"
refresh_token = "YOUR_DROPBOX_REFRESH_TOKEN"
folder = "/TradeJournalExports"
```

A temporary access token can still work for quick tests, but it may expire:

```toml
[dropbox]
access_token = "SHORT_LIVED_ACCESS_TOKEN"
folder = "/TradeJournalExports"
```

Then export/download your IBKR, Wealthsimple, or NinjaTrader CSVs into that Dropbox folder.
            """
        )

    folder = st.text_input("Dropbox folder path", value=default_folder or "/TradeJournalExports")
    if refresh_token and app_key and app_secret:
        status = "✅ Dropbox refresh-token auth configured"
    elif token:
        status = "⚠️ Temporary Dropbox access token found; it may expire"
    else:
        status = "❌ Missing Dropbox credentials in secrets"
    st.write("Status:", status)

    if st.button("Scan Dropbox Now", type="primary", disabled=not has_dropbox_auth):
        with st.spinner("Scanning Dropbox and importing new CSV files..."):
            try:
                download_dir = UPLOAD_DIR / "dropbox"
                downloaded = download_new_csvs(
                    folder,
                    download_dir,
                    access_token=token,
                    app_key=app_key,
                    app_secret=app_secret,
                    refresh_token=refresh_token,
                )
                if not downloaded:
                    st.info("No CSV files found in that Dropbox folder.")
                    return

                results = []
                for item in downloaded:
                    if has_imported_source_hash(user_id, "dropbox", item.content_hash):
                        results.append({
                            "file": item.name,
                            "status": "skipped_file_hash",
                            "parsed": 0,
                            "inserted": 0,
                            "skipped": 0,
                            "message": "Skipped already imported Dropbox file.",
                        })
                        continue
                    try:
                        results.append(import_one_csv_path(user_id, portfolio_id, item.local_path, "dropbox", item.content_hash))
                    except Exception as e:
                        results.append({
                            "file": item.name,
                            "status": "error",
                            "parsed": 0,
                            "inserted": 0,
                            "skipped": 0,
                            "message": str(e),
                        })

                st.subheader("Scan results")
                st.dataframe(pd.DataFrame(results), width="stretch", hide_index=True)
                st.success(f"Checked {len(downloaded)} file(s). Inserted {sum(r.get('inserted', 0) for r in results)} trade(s).")
            except Exception as e:
                st.error(f"Dropbox scan failed: {e}")

    st.info("Tip: this simple version scans when you click the button. On Streamlit Cloud, true background jobs are not reliable; for scheduled scans, deploy the same logic as a cron job on Render/Railway/GitHub Actions, or add Dropbox webhooks later.")

def render_monthly_calendar(df):
    section_heading("📅 Monthly P&L Calendar", "Calendar uses trade date, not settlement date. Platform totals are shown separately.")
    if df.empty or "date" not in df:
        st.info("No dated trades yet.")
        return
    dated = df.dropna(subset=["date"]).copy()
    if dated.empty:
        st.info("No trades with valid trade dates yet.")
        return
    dated["date"] = pd.to_datetime(dated["date"])
    dated["platform"] = dated["broker"].map(broker_platform_name)
    months = sorted(dated["date"].dt.to_period("M").astype(str).unique(), reverse=True)
    selected = st.selectbox("Calendar month", months, index=0)
    month_df = dated[dated["date"].dt.to_period("M").astype(str) == selected]
    total = month_df["realized_pl"].sum()
    wins = month_df.groupby(month_df["date"].dt.date)["realized_pl"].sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Monthly Total P&L", money(total))
    c2.metric("Winning-Day P&L", money(wins[wins > 0].sum()))
    c3.metric("Losing-Day P&L", money(wins[wins < 0].sum()))
    c4.metric("Trades This Month", int(len(month_df)))
    p1, p2, p3 = st.columns(3)
    platform = month_df.groupby("platform").agg(pnl=("realized_pl", "sum"), trades=("id", "count"))
    for col, name in zip([p1, p2, p3], ["IBKR", "NinjaTrader", "Wealthsimple"]):
        pnl = platform.loc[name, "pnl"] if name in platform.index else 0
        trades = platform.loc[name, "trades"] if name in platform.index else 0
        col.metric(f"{name} Monthly P&L", money(pnl), f"{int(trades)} trades")

    year, mon = map(int, selected.split("-"))
    cal = calendar.Calendar(firstweekday=0)
    daily = month_df.groupby(month_df["date"].dt.date).agg(pnl=("realized_pl", "sum"), trades=("id", "count"))
    daily_platform = month_df.groupby([month_df["date"].dt.date, "platform"])["realized_pl"].sum()
    st.caption("Calendar uses trade date, not settlement date.")
    cols = st.columns(7)
    for col, name in zip(cols, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        col.markdown(f"**{name}**")
    for week in cal.monthdatescalendar(year, mon):
        cols = st.columns(7)
        for col, day in zip(cols, week):
            if day.month != mon:
                col.markdown('<div class="calendar-cell" style="opacity:.25"></div>', unsafe_allow_html=True)
                continue
            pnl = daily.loc[day, "pnl"] if day in daily.index else 0
            trades = daily.loc[day, "trades"] if day in daily.index else 0
            bg = "rgba(34,197,94,.22)" if pnl > 0 else "rgba(239,68,68,.22)" if pnl < 0 else "rgba(148,163,184,.08)"
            platforms = []
            for name, short in [("IBKR", "IBKR"), ("NinjaTrader", "NT"), ("Wealthsimple", "WS")]:
                try:
                    val = daily_platform.loc[(day, name)]
                    if val:
                        platforms.append(f"<div class='small-platform'>{short}: {money(val)}</div>")
                except KeyError:
                    pass
            col.markdown(
                f"""
                <div class="calendar-cell" style="background:{bg}">
                  <div class="calendar-day">{day.day}</div>
                  <div class="muted">{int(trades)} trades</div>
                  <div class="calendar-pnl {'pos' if pnl > 0 else 'neg' if pnl < 0 else ''}">{money(pnl) if trades else '—'}</div>
                  {''.join(platforms)}
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")
    section_heading("Daily Trade Details", "Expand a date to see every trade included in that calendar day.")

    details = month_df.copy()
    details["day"] = details["date"].dt.date
    details = details.sort_values(["day", "broker", "symbol", "trade_datetime" if "trade_datetime" in details.columns else "date"])

    wanted_cols = [
        "broker", "symbol", "side", "quantity", "buy_price", "sell_price",
        "realized_pl", "commission", "setup_tag", "notes"
    ]
    visible_cols = [c for c in wanted_cols if c in details.columns]

    for day, day_df in details.groupby("day", sort=True):
        day_pnl = float(day_df["realized_pl"].sum()) if "realized_pl" in day_df else 0.0
        title = f"{day.strftime('%b %d, %Y')} — {len(day_df)} trade(s) — {money(day_pnl)}"
        with st.expander(title, expanded=False):
            display = day_df[visible_cols].copy()
            rename_map = {
                "broker": "Platform",
                "symbol": "Symbol",
                "side": "Side",
                "quantity": "Qty",
                "buy_price": "Buy",
                "sell_price": "Sell",
                "realized_pl": "P&L",
                "commission": "Fees",
                "setup_tag": "Setup",
                "notes": "Notes",
            }
            display = display.rename(columns={k: v for k, v in rename_map.items() if k in display.columns})
            st.dataframe(display, width="stretch", hide_index=True)


def main():
    init_db()
    st.sidebar.markdown("""
    <div class="sidebar-brand">
        <div class="sidebar-title">Trade Journal</div>
        <div class="sidebar-sub">Clean trading journal</div>
    </div>
    """, unsafe_allow_html=True)
    user_email = st.sidebar.text_input("User email", value=st.session_state.get("email", "streamlit@local"))
    st.session_state["email"] = user_email
    user_id = get_or_create_user(user_email)
    portfolios = get_portfolios(user_id)
    if not portfolios:
        get_or_create_portfolio(user_id)
        portfolios = get_portfolios(user_id)
    names = [p["name"] for p in portfolios]
    selected_name = st.sidebar.selectbox("Current portfolio", names)
    portfolio_id = next(p["id"] for p in portfolios if p["name"] == selected_name)
    new_portfolio = st.sidebar.text_input("Create portfolio")
    if st.sidebar.button("Add portfolio") and new_portfolio.strip():
        get_or_create_portfolio(user_id, new_portfolio.strip())
        st.rerun()
    st.sidebar.markdown(f"""
    <div class="portfolio-chip">
      <div class="muted">Current Portfolio</div>
      <div style="font-weight:950;font-size:16px;color:white;margin-top:4px;">{selected_name}</div>
    </div>
    """, unsafe_allow_html=True)
    st.sidebar.divider()
    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "Import", "Dropbox", "Trades", "Monthly", "Export"],
        label_visibility="collapsed",
    )
    df = load_trades_df(user_id, portfolio_id)

    if page == "Dashboard":
        render_hero("Dashboard", "Your key trading numbers, calendar, and next-session plan.", selected_name)

        pnl = df["realized_pl"].sum() if not df.empty else 0
        trade_count = len(df)
        wins = (df["realized_pl"] > 0).sum() if not df.empty else 0
        losses = (df["realized_pl"] < 0).sum() if not df.empty else 0
        win_rate = (wins / trade_count * 100) if trade_count else 0
        fees = abs(df["commission"].sum()) if not df.empty and "commission" in df else 0
        avg_trade = (pnl / trade_count) if trade_count else 0

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            render_metric("Total P&L", money(pnl), "pos" if pnl >= 0 else "neg")
        with c2:
            render_metric("Trades", f"{trade_count:,}")
        with c3:
            render_metric("Win Rate", f"{win_rate:.1f}%")
        with c4:
            render_metric("Avg Trade", money(avg_trade), "pos" if avg_trade >= 0 else "neg")

        st.write("")
        left, right = st.columns([0.66, 0.34], gap="large")
        with left:
            section_heading("Equity")
            if not df.empty and "date" in df:
                chart_df = df.dropna(subset=["date"]).sort_values("date").copy()
                chart_df["equity"] = chart_df["realized_pl"].cumsum()
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=chart_df["date"], y=chart_df["equity"], mode="lines", line=dict(color="#a78bfa", width=2), name="Equity"))
                fig.update_layout(height=320, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#eef2f7", xaxis=dict(gridcolor="#252c37"), yaxis=dict(gridcolor="#252c37"))
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            else:
                st.info("Import trades to build your equity chart.")

        with right:
            section_heading("Summary")
            s1, s2 = st.columns(2)
            s1.metric("Winning Trades", int(wins))
            s2.metric("Losing Trades", int(losses))
            s3, s4 = st.columns(2)
            s3.metric("Fees", money(fees))
            s4.metric("Platforms", df["broker"].nunique() if not df.empty and "broker" in df else 0)
            plan = generate_tomorrow_plan(df)
            st.markdown("<hr>", unsafe_allow_html=True)
            st.markdown(f"**Tomorrow:** {plan['mode']}")
            st.caption(plan["reason"])

        st.write("")
        render_monthly_calendar(df)

        st.write("")
        section_heading("Tomorrow Trading Plan")
        plan = generate_tomorrow_plan(df)
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Mode", plan["mode"])
        t2.metric("Best Setup", plan["best_setup"])
        t3.metric("Avoid", plan["avoid_setup"])
        t4.metric("Confidence", f"{plan['confidence']}%")

    elif page == "Import":
        render_hero("Import", "Upload broker CSV files.", selected_name)
        files = st.file_uploader("Upload CSV files", type=["csv"], accept_multiple_files=True)
        if st.button("Import uploaded files", type="primary"):
            if not files:
                st.warning("Upload at least one CSV.")
            else:
                for f in files:
                    path = UPLOAD_DIR / f.name
                    path.write_bytes(f.getbuffer())
                    digest = file_hash(path)
                    conn = connect()
                    exists = conn.execute("SELECT id FROM imported_files WHERE user_id=? AND source=? AND file_hash=?", (user_id, "streamlit_upload", digest)).fetchone()
                    conn.close()
                    if exists:
                        st.info(f"Skipped already imported file: {f.name}")
                        continue
                    try:
                        import_type, trades = parse_uploaded_file(path)
                        trades = prepare_trades_for_import(user_id, portfolio_id, import_type, trades)
                        batch_id = f"ST_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
                        inserted, skipped = insert_trades(user_id, portfolio_id, trades, f.name, batch_id)
                        conn = connect()
                        conn.execute("INSERT OR IGNORE INTO imported_files(user_id, source, file_name, file_hash, batch_id, parsed_count, inserted_count, skipped_count, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (user_id, "streamlit_upload", f.name, digest, batch_id, len(trades), inserted, skipped, "OK"))
                        conn.commit(); conn.close()
                        st.success(f"{f.name}: parsed {len(trades)}, inserted {inserted}, skipped {skipped} ({import_type})")
                    except Exception as e:
                        st.error(f"{f.name}: {e}")

        st.divider()
        section_heading("Delete old import batch")
        st.caption("Use this before re-importing a corrected Wealthsimple/NinjaTrader/IBKR file. It also clears the saved file hash, so the same CSV can be imported again.")
        batches = get_import_batches(user_id, portfolio_id)
        if not batches:
            st.info("No import batches found for this portfolio.")
        else:
            batch_df = pd.DataFrame(batches)
            show_cols = [
                "batch_id", "source", "file_name", "broker", "trade_count", "pnl",
                "first_trade_date", "last_trade_date", "inserted_count", "skipped_count", "imported_at", "status"
            ]
            st.dataframe(batch_df[[c for c in show_cols if c in batch_df.columns]], width="stretch", hide_index=True)

            def batch_label(item):
                name = item.get("file_name") or item.get("broker") or "batch"
                return f"{item['batch_id']} | {name} | trades: {item.get('trade_count', 0)} | P&L: {money(item.get('pnl', 0))}"

            selected_batch = st.selectbox(
                "Select batch to delete",
                options=batches,
                format_func=batch_label,
                key="delete_batch_select",
            )
            confirm_delete = st.checkbox(
                "I understand this will delete all trades from the selected batch and clear its import history.",
                key="confirm_delete_batch",
            )
            if st.button("Delete selected batch", type="primary", disabled=not confirm_delete):
                result = delete_import_batch(user_id, portfolio_id, selected_batch["batch_id"])
                st.success(
                    f"Deleted batch {selected_batch['batch_id']}: "
                    f"{result['trades_deleted']} trades removed, "
                    f"{result['file_records_deleted']} import-history record(s) removed."
                )
                st.rerun()

    elif page == "Dropbox":
        render_dropbox_import_page(user_id, portfolio_id)

    elif page == "Trades":
        render_hero("Trades", "Compact table of your imported trades.", selected_name)
        if df.empty:
            st.info("No trades yet.")
        else:
            cols = ["id", "broker", "symbol", "trade_datetime", "quantity", "side", "buy_price", "sell_price", "realized_pl", "setup_tag", "journal_note"]
            st.dataframe(df[[c for c in cols if c in df.columns]], width="stretch", hide_index=True)

    elif page == "Monthly":
        render_hero("Monthly", "Monthly P&L and trade counts.", selected_name)
        if df.empty:
            st.info("No trades yet.")
        else:
            monthly = df.dropna(subset=["month"]).groupby("month").agg(realized_pl=("realized_pl", "sum"), fees=("commission", "sum"), trades=("id", "count")).reset_index()
            st.dataframe(monthly, width="stretch", hide_index=True)
            st.plotly_chart(px.bar(monthly, x="month", y="realized_pl", title="Monthly P&L"), width="stretch")

    elif page == "Export":
        render_hero("Export", "Download your filtered journal data.", selected_name)
        if df.empty:
            st.info("Nothing to export.")
        else:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download trades CSV", csv, "trades_export.csv", "text/csv")

    else:
        render_hero("📁 Folder import notes", "Local folder scanning versus cloud deployment.", selected_name)
        st.info("Streamlit Cloud cannot watch folders on your local computer. For deployed use, upload CSVs on the Import page. Folder auto-import only works when running Streamlit locally on the same machine as the export folders.")
        folder = st.text_input("Local folder to scan (local-only)")
        if st.button("Scan local folder") and folder:
            folder_path = Path(folder).expanduser()
            if not folder_path.exists():
                st.error("Folder not found.")
            else:
                files = list(folder_path.glob("*.csv"))
                st.write(f"Found {len(files)} CSV file(s). Use the Import page for cloud deployment.")


if __name__ == "__main__":
    main()
