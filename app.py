from __future__ import annotations

from pathlib import Path
from datetime import date, datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

from spy_option_backtester.backtest import BacktestConfig, run_long_option_backtest
from spy_option_backtester.massive_client import MassiveClient
from spy_option_backtester.plotting import plot_equity_curve
from spy_option_backtester.tickers import build_option_ticker
from ibkr_live import get_live_quotes, get_live_quotes_multi

load_dotenv()

st.set_page_config(page_title="SPY Options Backtester + IBKR Live", page_icon="📈", layout="wide")

st.title("SPY Options Backtester + IBKR Live P&L")
st.caption("One project: Massive historical backtesting + native IBKR live P&L tracking. Read-only. No trades are placed.")

backtest_tab, live_tab, setup_tab = st.tabs(["Historical Backtest", "IBKR Live P&L", "Setup Notes"])


def fmt_money(value):
    return "N/A" if value is None else f"${float(value):,.2f}"


with backtest_tab:
    st.subheader("Massive Historical Options Backtest")
    st.caption("Backtest single-leg options using Massive historical aggregate candles. Includes SPY price at entry/exit, limit-fill time, and SL/TP buttons.")

    with st.sidebar:
        st.header("Backtest Settings")
        st.subheader("Contract")
        bt_underlying = st.text_input("Underlying", value="SPY", key="bt_underlying").upper().strip()
        bt_expiry = st.date_input("Expiry", value=date(2026, 5, 8), key="bt_expiry")
        bt_right_label = st.radio("Option Type", ["Call", "Put"], horizontal=True, key="bt_right_label")
        bt_right = "C" if bt_right_label == "Call" else "P"
        bt_strike = st.number_input("Strike", min_value=0.0, value=735.0, step=1.0, key="bt_strike")

        st.subheader("Historical Range")
        bt_from_date = st.date_input("From date", value=date(2026, 5, 1), key="bt_from")
        bt_to_date = st.date_input("To date", value=date(2026, 5, 8), key="bt_to")
        bt_interval = st.number_input("Interval", min_value=1, value=1, step=1, key="bt_interval")
        bt_timespan = st.selectbox("Timespan", ["minute", "hour", "day", "week", "month", "quarter", "year"], index=0, key="bt_timespan")

        st.subheader("Strategy")
        bt_entry_time = st.text_input("Entry time", value="09:35", key="bt_entry_time")
        bt_use_limit_entry = st.checkbox("Use limit entry price", value=False, key="bt_use_limit")
        bt_entry_limit_price = st.number_input("Entry limit price", min_value=0.0, value=2.50, step=0.01, format="%.2f", disabled=not bt_use_limit_entry, key="bt_limit_price")
        bt_exit_time = st.text_input("Exit time", value="15:55", key="bt_exit_time")

        st.subheader("Risk Controls")
        if "bt_stop_loss_pct" not in st.session_state:
            st.session_state.bt_stop_loss_pct = 35.0
        if "bt_take_profit_pct" not in st.session_state:
            st.session_state.bt_take_profit_pct = 80.0

        bt_step_pct = st.selectbox("Button step", [1.0, 2.5, 5.0, 10.0], index=0, format_func=lambda x: f"{x:g}%", key="bt_step_pct")

        st.caption("Stop Loss")
        sl_minus, sl_value, sl_plus = st.columns([1, 2, 1])
        with sl_minus:
            if st.button("−", key="bt_sl_down", use_container_width=True):
                st.session_state.bt_stop_loss_pct = max(0.0, st.session_state.bt_stop_loss_pct - bt_step_pct)
        with sl_value:
            bt_stop_loss_pct = st.number_input("Stop loss %", min_value=0.0, max_value=100.0, step=bt_step_pct, key="bt_stop_loss_pct")
        with sl_plus:
            if st.button("+", key="bt_sl_up", use_container_width=True):
                st.session_state.bt_stop_loss_pct = min(100.0, st.session_state.bt_stop_loss_pct + bt_step_pct)

        st.caption("Take Profit")
        tp_minus, tp_value, tp_plus = st.columns([1, 2, 1])
        with tp_minus:
            if st.button("−", key="bt_tp_down", use_container_width=True):
                st.session_state.bt_take_profit_pct = max(0.0, st.session_state.bt_take_profit_pct - bt_step_pct)
        with tp_value:
            bt_take_profit_pct = st.number_input("Take profit %", min_value=0.0, step=bt_step_pct, key="bt_take_profit_pct")
        with tp_plus:
            if st.button("+", key="bt_tp_up", use_container_width=True):
                st.session_state.bt_take_profit_pct = st.session_state.bt_take_profit_pct + bt_step_pct

        bt_contracts = st.number_input("Contracts", min_value=1, value=1, step=1, key="bt_contracts")
        bt_starting_cash = st.number_input("Starting cash", min_value=0.0, value=10000.0, step=500.0, key="bt_cash")
        bt_commission = st.number_input("Commission / contract", min_value=0.0, value=0.65, step=0.05, key="bt_commission")

    option_ticker = build_option_ticker(bt_underlying, str(bt_expiry), bt_right, bt_strike)
    st.info(f"Option ticker: `{option_ticker}`")

    if st.button("Run Historical Backtest", type="primary", key="run_bt"):
        try:
            client = MassiveClient()
            with st.spinner("Fetching option candles from Massive..."):
                option_candles = client.get_aggregates(
                    ticker=option_ticker,
                    multiplier=int(bt_interval),
                    timespan=bt_timespan,
                    from_date=str(bt_from_date),
                    to_date=str(bt_to_date),
                )
            with st.spinner(f"Fetching {bt_underlying} candles from Massive..."):
                underlying_candles = client.get_aggregates(
                    ticker=bt_underlying,
                    multiplier=int(bt_interval),
                    timespan=bt_timespan,
                    from_date=str(bt_from_date),
                    to_date=str(bt_to_date),
                )

            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)
            option_candles.to_csv(output_dir / "option_candles.csv", index=False)
            underlying_candles.to_csv(output_dir / "underlying_candles.csv", index=False)

            config = BacktestConfig(
                contracts=int(bt_contracts),
                entry_time=bt_entry_time,
                exit_time=bt_exit_time,
                stop_loss=float(bt_stop_loss_pct) / 100,
                take_profit=float(bt_take_profit_pct) / 100,
                starting_cash=float(bt_starting_cash),
                commission_per_contract=float(bt_commission),
                entry_limit_price=float(bt_entry_limit_price) if bt_use_limit_entry else None,
            )
            trades, equity = run_long_option_backtest(option_candles, config, underlying_candles=underlying_candles)
            trades.to_csv(output_dir / "trades.csv", index=False)
            equity.to_csv(output_dir / "equity_curve.csv", index=False)
            plot_equity_curve(equity, output_dir / "equity_curve.png")

            st.success("Backtest complete. Files saved in the output folder.")

            if not trades.empty:
                total_pnl = float(trades["net_pnl"].sum())
                winning = trades[trades["net_pnl"] > 0]
                win_rate = len(winning) / len(trades) * 100 if len(trades) else 0
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total net P&L", f"${total_pnl:,.2f}")
                m2.metric("Trades", str(len(trades)))
                m3.metric("Win rate", f"{win_rate:.1f}%")
                m4.metric("Final cash", f"${float(trades['cash_after_trade'].iloc[-1]):,.2f}")

                st.markdown("#### Trades")
                st.dataframe(trades, use_container_width=True)

                csv = trades.to_csv(index=False).encode("utf-8")
                st.download_button("Download trades.csv", csv, "trades.csv", "text/csv")

            if not equity.empty:
                st.markdown("#### Equity Curve")
                st.line_chart(equity.set_index("timestamp")["equity"])

            with st.expander("Raw candle samples"):
                st.markdown("##### Option candles")
                st.dataframe(option_candles.head(50), use_container_width=True)
                st.markdown("##### Underlying candles")
                st.dataframe(underlying_candles.head(50), use_container_width=True)
        except Exception as e:
            st.error(f"Backtest failed: {e}")


with live_tab:
    st.subheader("IBKR Multi-Option Live P&L Tracker")
    st.caption("Track several option contracts at the same time using native IBKR API. Read-only. No trades are placed.")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        host = st.text_input("Host", value="127.0.0.1", key="live_host")
        port = st.selectbox(
            "Port",
            options=[7497, 7496, 4002, 4001],
            index=0,
            key="live_port",
            help="7497=TWS paper, 7496=TWS live, 4002=Gateway paper, 4001=Gateway live",
        )
        use_delayed = st.checkbox("Use delayed data", value=False, key="live_delayed")
    with col_b:
        wait_seconds = st.slider("Quote wait seconds", 2.0, 15.0, 5.0, 0.5, key="live_wait")
        client_id = st.number_input("Client ID", value=0, step=1, key="live_client_id", help="Use 0 for random client ID")
        auto_update = st.checkbox("Auto update quotes", value=False, key="live_auto_update")
        refresh_interval = st.selectbox("Auto update every", [5, 10, 15, 30, 60], index=1, format_func=lambda x: f"{x} seconds", key="live_refresh_interval", disabled=not auto_update)
    with col_c:
        st.info("Add/edit rows below, then click Refresh. Turn on Auto update for repeated live refreshes.")
        if auto_update and st_autorefresh is None:
            st.warning("Auto update package is missing. Run: python -m pip install streamlit-autorefresh")

    st.markdown("#### Option positions")

    default_positions = pd.DataFrame([
        {
            "delete": False,
            "enabled": True,
            "underlying": "SPY",
            "expiry": date(2026, 5, 8),
            "right": "C",
            "strike": 735.0,
            "entry_price": 0.00,
            "contracts": 1,
            "stop_loss_pct": 35.0,
            "take_profit_pct": 70.0,
        },
        {
            "delete": False,
            "enabled": False,
            "underlying": "SPY",
            "expiry": date(2026, 5, 8),
            "right": "C",
            "strike": 740.0,
            "entry_price": 0.00,
            "contracts": 1,
            "stop_loss_pct": 35.0,
            "take_profit_pct": 70.0,
        },
    ])

    if "positions_df" not in st.session_state:
        st.session_state.positions_df = default_positions.copy()

    # Keep expiry editable through a real calendar date selector instead of free-text.
    editor_source_df = st.session_state.positions_df.copy()
    if "expiry" in editor_source_df.columns:
        editor_source_df["expiry"] = pd.to_datetime(editor_source_df["expiry"], errors="coerce").dt.date

    positions_df = st.data_editor(
        editor_source_df,
        num_rows="dynamic",
        use_container_width=True,
        key="multi_positions_editor",
        column_config={
            "delete": st.column_config.CheckboxColumn("Delete", default=False, help="Check this, then click Delete selected positions."),
            "enabled": st.column_config.CheckboxColumn("Track", default=True),
            "underlying": st.column_config.TextColumn("Underlying", help="Example: SPY"),
            "expiry": st.column_config.DateColumn("Expiry", help="Use the calendar picker", format="YYYY-MM-DD"),
            "right": st.column_config.SelectboxColumn("C/P", options=["C", "P"]),
            "strike": st.column_config.NumberColumn("Strike", min_value=0.0, step=1.0, format="%.2f"),
            "entry_price": st.column_config.NumberColumn("Entry price", min_value=0.0, step=0.01, format="%.2f"),
            "contracts": st.column_config.NumberColumn("Contracts", min_value=1, step=1),
            "stop_loss_pct": st.column_config.NumberColumn("SL %", min_value=0.0, step=1.0, format="%.1f"),
            "take_profit_pct": st.column_config.NumberColumn("TP %", min_value=0.0, step=1.0, format="%.1f"),
        },
    )

    # Persist table edits across manual and automatic Streamlit reruns.
    st.session_state.positions_df = positions_df.copy()

    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
    with btn_col1:
        delete_selected = st.button("Delete selected positions", key="delete_selected_positions")
    with btn_col2:
        reset_positions = st.button("Reset positions", key="reset_positions")

    if delete_selected:
        if "delete" in positions_df.columns:
            cleaned = positions_df[~positions_df["delete"].fillna(False).astype(bool)].copy()
            cleaned["delete"] = False
            st.session_state.positions_df = cleaned.reset_index(drop=True)
            st.rerun()
    if reset_positions:
        st.session_state.positions_df = default_positions.copy()
        st.rerun()

    auto_refresh_count = None
    if auto_update and st_autorefresh is not None:
        auto_refresh_count = st_autorefresh(
            interval=int(refresh_interval) * 1000,
            key="ibkr_live_auto_refresh",
            limit=None,
        )

    refresh = st.button("Refresh All IBKR Quotes", type="primary", key="refresh_ibkr_multi")
    should_refresh = refresh or (auto_update and st_autorefresh is not None and auto_refresh_count is not None)

    if should_refresh:
        refresh_df = positions_df.copy()
        if "delete" in refresh_df.columns:
            refresh_df = refresh_df[~refresh_df["delete"].fillna(False).astype(bool)].drop(columns=["delete"])
        if "expiry" in refresh_df.columns:
            refresh_df["expiry"] = pd.to_datetime(refresh_df["expiry"], errors="coerce").dt.strftime("%Y-%m-%d")
        positions = refresh_df.to_dict("records")
        with st.spinner("Connecting to IBKR and requesting multiple option quotes..."):
            result = get_live_quotes_multi(
                host=host,
                port=int(port),
                client_id=None if int(client_id) == 0 else int(client_id),
                positions=positions,
                wait_seconds=float(wait_seconds),
                use_delayed_data=use_delayed,
            )

        if not result.get("ok"):
            st.error(result.get("error", "IBKR quote request failed."))
            for msg in result.get("messages", []):
                st.warning(msg)
        else:
            rows = result.get("rows", [])
            results_df = pd.DataFrame(rows)

            st.caption(
                f"Data requested: {result.get('market_data_type_requested', 'unknown')} | "
                f"Snapshot UTC: {result.get('snapshot_time_utc', 'N/A')} | "
                f"Client ID: {result.get('client_id', 'N/A')}"
            )
            if auto_update:
                st.caption(f"Auto update is ON: refreshing every {refresh_interval} seconds.")

            total_pnl = results_df["unrealized_pnl"].dropna().sum() if "unrealized_pnl" in results_df.columns else 0.0
            tracked = len(results_df)
            winners = int((results_df["unrealized_pnl"] > 0).sum()) if "unrealized_pnl" in results_df.columns else 0
            missing_prices = int(results_df["option_price"].isna().sum()) if "option_price" in results_df.columns else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total unrealized P&L", f"${total_pnl:,.2f}")
            m2.metric("Positions tracked", str(tracked))
            m3.metric("Positions green", str(winners))
            m4.metric("Missing option prices", str(missing_prices))

            if missing_prices:
                st.warning("Some option prices were not returned. Try delayed data, increase quote wait seconds, or check OPRA/options data permissions.")

            fallback_close = results_df[
                (results_df.get("option_price_source") == "close")
                & results_df.get("option_bid").isna()
                & results_df.get("option_ask").isna()
            ] if not results_df.empty else pd.DataFrame()
            if not fallback_close.empty:
                st.warning("At least one option is using close price because live bid/ask was not returned. P&L may not reflect current live value.")

            st.markdown("#### Multi-position P&L")
            display_cols = [
                "status", "underlying", "expiry", "right", "strike", "contracts", "entry_price",
                "option_price", "option_price_source", "unrealized_pnl", "unrealized_pnl_pct",
                "stop_price", "take_profit_price", "spy_price", "spy_price_source", "quote_time_utc",
            ]
            st.dataframe(
                results_df[[c for c in display_cols if c in results_df.columns]],
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("#### Quote breakdown")
            quote_cols = [
                "underlying", "expiry", "right", "strike", "option_bid", "option_ask",
                "option_midpoint", "option_last", "option_close", "option_price", "option_price_source",
                "spy_price", "quote_time_utc",
            ]
            st.dataframe(
                results_df[[c for c in quote_cols if c in results_df.columns]],
                use_container_width=True,
                hide_index=True,
            )

            csv = results_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download live_positions.csv", csv, "live_positions.csv", "text/csv")

            messages = result.get("messages", [])
            if messages:
                with st.expander("IBKR messages"):
                    for msg in messages:
                        st.write(msg)

    with st.expander("How to add multiple options"):
        st.markdown(
            """
- Add a new row in the table for every contract you want to track.
- Keep `enabled` checked only for rows you want to refresh.
- Use expiry format `YYYY-MM-DD`.
- Enter your real option fill under `entry_price`; P&L is calculated from that.
- The app connects to IBKR once per refresh and requests all enabled rows together.
"""
        )


with setup_tab:
    st.markdown(
        """
## Setup

### 1. Install packages

Open PowerShell inside this folder and run:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Or double-click:

```text
run_ui.bat
```

### 2. Massive setup for Historical Backtest

Create a file named `.env` in this project folder:

```text
MASSIVE_API_KEY=your_api_key_here
```

The backtest tab uses Massive historical aggregate candles for both the option contract and the underlying SPY candles.

### 3. IBKR setup for Live P&L

Open TWS or IB Gateway first, then enable API access:

```text
File → Global Configuration → API → Settings → Enable ActiveX and Socket Clients
```

Common ports:

| Platform | Paper | Live |
|---|---:|---:|
| TWS | 7497 | 7496 |
| IB Gateway | 4002 | 4001 |

If you do not have live OPRA/options data permissions, check **Use delayed data** in the live tab.

### Notes

- This app is read-only. It does not place, modify, or cancel trades.
- For live P&L, the app uses option midpoint first, then last, then close as fallback.
- For historical backtests, output files are saved into the `output/` folder.
"""
    )
