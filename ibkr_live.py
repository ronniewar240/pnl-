"""
Native IBKR live quote helper for Streamlit.

This file intentionally uses Interactive Brokers' official `ibapi` package,
not `ib_insync`, so Streamlit does not run into asyncio/event-loop errors like:
- There is no current event loop in thread 'ScriptRunner.scriptThread'
- Timeout should be used inside a task
- coroutine 'Connection.connectAsync' was never awaited

Read-only market data only. It does NOT place orders.
"""

from __future__ import annotations

import random
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Any

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract


@dataclass
class Quote:
    symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    close: Optional[float] = None
    midpoint: Optional[float] = None
    market_price: Optional[float] = None
    market_price_source: Optional[str] = None
    snapshot_time_utc: Optional[str] = None
    bid_time_utc: Optional[str] = None
    ask_time_utc: Optional[str] = None
    last_time_utc: Optional[str] = None
    close_time_utc: Optional[str] = None

    def calculate_market_price(self) -> Optional[float]:
        # Prefer midpoint when bid/ask are valid, then last, then close.
        if self.bid is not None and self.ask is not None and self.bid > 0 and self.ask > 0:
            self.midpoint = round((self.bid + self.ask) / 2, 4)
            self.market_price = self.midpoint
            self.market_price_source = "midpoint"
        elif self.last is not None and self.last > 0:
            self.midpoint = None
            self.market_price = self.last
            self.market_price_source = "last"
        elif self.close is not None and self.close > 0:
            self.midpoint = None
            self.market_price = self.close
            self.market_price_source = "close"
        else:
            self.midpoint = None
            self.market_price = None
            self.market_price_source = None
        return self.market_price


class IBKRQuoteApp(EWrapper, EClient):
    def __init__(self) -> None:
        EClient.__init__(self, self)
        self.connected_event = threading.Event()
        self.error_messages = []
        self.quotes: Dict[int, Quote] = {}
        self.req_symbols: Dict[int, str] = {}

    def nextValidId(self, orderId: int) -> None:  # noqa: N802 - IBKR naming
        self.connected_event.set()

    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str = "") -> None:  # noqa: N802
        # Ignore common market data farm connection info codes.
        informational = {2104, 2106, 2158, 2107, 2108}
        if errorCode not in informational:
            self.error_messages.append(f"IBKR error {errorCode} on reqId {reqId}: {errorString}")

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib) -> None:  # noqa: N802
        if price is None or price < 0:
            return
        quote = self.quotes.setdefault(reqId, Quote(symbol=self.req_symbols.get(reqId, str(reqId))))
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        quote.snapshot_time_utc = now

        # Tick types: 1 bid, 2 ask, 4 last, 9 close
        if tickType == 1:
            quote.bid = price
            quote.bid_time_utc = now
        elif tickType == 2:
            quote.ask = price
            quote.ask_time_utc = now
        elif tickType == 4:
            quote.last = price
            quote.last_time_utc = now
        elif tickType == 9:
            quote.close = price
            quote.close_time_utc = now
        quote.calculate_market_price()


def stock_contract(symbol: str) -> Contract:
    c = Contract()
    c.symbol = symbol.upper().strip()
    c.secType = "STK"
    c.exchange = "SMART"
    c.currency = "USD"
    return c


def option_contract(underlying: str, expiry: str, right: str, strike: float) -> Contract:
    c = Contract()
    c.symbol = underlying.upper().strip()
    c.secType = "OPT"
    c.exchange = "SMART"
    c.currency = "USD"
    c.lastTradeDateOrContractMonth = expiry.replace("-", "")  # YYYYMMDD
    c.strike = float(strike)
    c.right = right.upper().strip()[0]  # C or P
    c.multiplier = "100"
    return c


def get_live_quotes(
    host: str,
    port: int,
    client_id: Optional[int],
    underlying: str,
    expiry: str,
    right: str,
    strike: float,
    wait_seconds: float = 4.0,
    use_delayed_data: bool = False,
) -> Dict[str, Any]:
    """
    Connects to TWS / IB Gateway, pulls SPY stock + option quote, then disconnects.
    This avoids keeping a persistent IBKR socket inside Streamlit reruns.
    """

    app = IBKRQuoteApp()
    client_id = client_id or random.randint(1000, 999999)

    app.connect(host, int(port), int(client_id))
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()

    if not app.connected_event.wait(timeout=8):
        try:
            app.disconnect()
        except Exception:
            pass
        return {
            "ok": False,
            "error": "Could not connect to IBKR. Make sure TWS/IB Gateway is open, API is enabled, and the port is correct.",
            "messages": app.error_messages,
        }

    # 1 = live, 3 = delayed, 4 = delayed frozen. Use delayed if user lacks live subscription.
    app.reqMarketDataType(3 if use_delayed_data else 1)

    stock_req_id = 101
    opt_req_id = 102
    app.req_symbols[stock_req_id] = underlying.upper().strip()
    app.req_symbols[opt_req_id] = f"{underlying.upper().strip()} {expiry} {right.upper()[0]} {strike}"

    app.quotes[stock_req_id] = Quote(symbol=app.req_symbols[stock_req_id])
    app.quotes[opt_req_id] = Quote(symbol=app.req_symbols[opt_req_id])

    # Generic tick list left blank for basic Level 1 bid/ask/last.
    app.reqMktData(stock_req_id, stock_contract(underlying), "", False, False, [])
    app.reqMktData(opt_req_id, option_contract(underlying, expiry, right, strike), "", False, False, [])

    time.sleep(float(wait_seconds))

    try:
        app.cancelMktData(stock_req_id)
        app.cancelMktData(opt_req_id)
    except Exception:
        pass

    stock_quote = app.quotes.get(stock_req_id, Quote(symbol=underlying.upper().strip()))
    option_quote = app.quotes.get(opt_req_id, Quote(symbol=f"{underlying} {expiry} {right} {strike}"))
    stock_quote.calculate_market_price()
    option_quote.calculate_market_price()

    try:
        app.disconnect()
    except Exception:
        pass

    return {
        "ok": True,
        "underlying_quote": asdict(stock_quote),
        "option_quote": asdict(option_quote),
        "messages": app.error_messages,
        "client_id": client_id,
        "market_data_type_requested": "delayed" if use_delayed_data else "live",
        "snapshot_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def get_live_quotes_multi(
    host: str,
    port: int,
    client_id: Optional[int],
    positions: list[dict],
    wait_seconds: float = 4.0,
    use_delayed_data: bool = False,
) -> Dict[str, Any]:
    """
    Connects once to TWS / IB Gateway and pulls quotes for multiple option positions.
    Each position dict should include: underlying, expiry, right, strike, entry_price, contracts,
    stop_loss_pct, take_profit_pct.
    """
    clean_positions = []
    for idx, p in enumerate(positions):
        if not p.get("enabled", True):
            continue
        try:
            underlying = str(p.get("underlying", "SPY")).upper().strip()
            expiry = str(p.get("expiry", "")).strip()
            right = str(p.get("right", "C")).upper().strip()[0]
            strike = float(p.get("strike"))
            if not underlying or not expiry or right not in {"C", "P"}:
                continue
            clean_positions.append({
                "row_id": idx + 1,
                "underlying": underlying,
                "expiry": expiry,
                "right": right,
                "strike": strike,
                "entry_price": float(p.get("entry_price", 0) or 0),
                "contracts": int(p.get("contracts", 1) or 1),
                "stop_loss_pct": float(p.get("stop_loss_pct", 0) or 0),
                "take_profit_pct": float(p.get("take_profit_pct", 0) or 0),
            })
        except Exception:
            continue

    if not clean_positions:
        return {"ok": False, "error": "No valid option rows were provided.", "messages": []}

    app = IBKRQuoteApp()
    client_id = client_id or random.randint(1000, 999999)

    app.connect(host, int(port), int(client_id))
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()

    if not app.connected_event.wait(timeout=8):
        try:
            app.disconnect()
        except Exception:
            pass
        return {
            "ok": False,
            "error": "Could not connect to IBKR. Make sure TWS/IB Gateway is open, API is enabled, and the port is correct.",
            "messages": app.error_messages,
        }

    app.reqMarketDataType(3 if use_delayed_data else 1)

    req_id = 1000
    underlying_req_ids: dict[str, int] = {}
    option_req_ids: dict[int, int] = {}

    # Request each unique underlying once.
    for underlying in sorted({p["underlying"] for p in clean_positions}):
        req_id += 1
        underlying_req_ids[underlying] = req_id
        app.req_symbols[req_id] = underlying
        app.quotes[req_id] = Quote(symbol=underlying)
        app.reqMktData(req_id, stock_contract(underlying), "", False, False, [])

    # Request each option row.
    for p in clean_positions:
        req_id += 1
        option_req_ids[p["row_id"]] = req_id
        sym = f"{p['underlying']} {p['expiry']} {p['right']} {p['strike']:g}"
        app.req_symbols[req_id] = sym
        app.quotes[req_id] = Quote(symbol=sym)
        app.reqMktData(
            req_id,
            option_contract(p["underlying"], p["expiry"], p["right"], p["strike"]),
            "",
            False,
            False,
            [],
        )

    time.sleep(float(wait_seconds))

    # Cancel all market data requests.
    for rid in list(underlying_req_ids.values()) + list(option_req_ids.values()):
        try:
            app.cancelMktData(rid)
        except Exception:
            pass

    rows = []
    for p in clean_positions:
        uq = app.quotes.get(underlying_req_ids[p["underlying"]], Quote(symbol=p["underlying"]))
        oq = app.quotes.get(option_req_ids[p["row_id"]], Quote(symbol=f"{p['underlying']} {p['expiry']} {p['right']} {p['strike']:g}"))
        uq.calculate_market_price()
        oq.calculate_market_price()
        option_price = oq.market_price
        entry_price = p["entry_price"]
        contracts = p["contracts"]

        pnl = None
        pnl_pct = None
        stop_price = None
        take_profit_price = None
        status = "Enter entry price"
        if option_price is None:
            status = "No option price"
        elif entry_price > 0:
            pnl = (float(option_price) - entry_price) * 100 * contracts
            pnl_pct = ((float(option_price) - entry_price) / entry_price) * 100
            stop_price = entry_price * (1 - p["stop_loss_pct"] / 100)
            take_profit_price = entry_price * (1 + p["take_profit_pct"] / 100)
            if p["stop_loss_pct"] > 0 and float(option_price) <= stop_price:
                status = "Stop loss hit"
            elif p["take_profit_pct"] > 0 and float(option_price) >= take_profit_price:
                status = "Take profit hit"
            else:
                status = "Open"

        rows.append({
            **p,
            "spy_price": uq.market_price,
            "spy_price_source": uq.market_price_source,
            "option_bid": oq.bid,
            "option_ask": oq.ask,
            "option_midpoint": oq.midpoint,
            "option_last": oq.last,
            "option_close": oq.close,
            "option_price": option_price,
            "option_price_source": oq.market_price_source,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pnl_pct,
            "stop_price": stop_price,
            "take_profit_price": take_profit_price,
            "status": status,
            "quote_time_utc": oq.snapshot_time_utc or uq.snapshot_time_utc,
        })

    try:
        app.disconnect()
    except Exception:
        pass

    return {
        "ok": True,
        "rows": rows,
        "messages": app.error_messages,
        "client_id": client_id,
        "market_data_type_requested": "delayed" if use_delayed_data else "live",
        "snapshot_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
