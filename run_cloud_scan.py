import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta
import yfinance as yf
import pandas as pd
import numpy as np

IST = timezone(timedelta(hours=5, minutes=30))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_FILE = os.path.join(BASE_DIR, "screener_database.json")
INTEL_FILE = os.path.join(BASE_DIR, "intelligence_cache.json")
SECTOR_FILE = os.path.join(BASE_DIR, "sector_master_cache.json")
STOCK_LIST_FILE = os.path.join(BASE_DIR, "stock_list_1452.txt")

def log(msg):
    ts = datetime.now(IST).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def load_sectors():
    if os.path.exists(SECTOR_FILE):
        try:
            with open(SECTOR_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"Error loading sectors: {e}")
    return {}

def load_symbols():
    if os.path.exists(STOCK_LIST_FILE):
        with open(STOCK_LIST_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip().upper() for line in f if line.strip()]
            # Filter ETF/BE/indices
            clean = []
            for s in lines:
                s = s.replace(".NS", "")
                if s.endswith("-BE") or s.endswith(".BO") or "NIFTY" in s or "ETF" in s or "GOLD" in s:
                    continue
                clean.append(s)
            return sorted(list(set(clean)))
    return []

def calculate_ema(series, period=10):
    return series.ewm(span=period, adjust=False).mean()

def scan_symbol(symbol, sector_db):
    yf_symbol = f"{symbol}.NS"
    try:
        ticker = yf.Ticker(yf_symbol)
        df_month = ticker.history(period="3y", interval="1mo")
        if df_month.empty or len(df_month) < 12:
            return None

        # Clean monthly bars
        df_month = df_month[df_month["Volume"] > 0]
        if len(df_month) < 12:
            return None

        closes = df_month["Close"]
        highs = df_month["High"]
        lows = df_month["Low"]
        opens = df_month["Open"]

        # Calculate Monthly 10-EMA
        ema10 = calculate_ema(closes, 10)
        curr_ema = float(ema10.iloc[-1])
        ltp = float(closes.iloc[-1])

        # Diff % to 10 EMA
        diff_pct = round(((ltp - curr_ema) / curr_ema) * 100, 2)

        # 12-Month 20%+ Momentum Check
        # Price moved >= 20% in at least 1 month during the last 12 months
        last_12 = df_month.tail(13)
        max_surge = 0.0
        surge_detected = False
        for i in range(1, len(last_12)):
            prev_c = last_12["Close"].iloc[i-1]
            curr_h = last_12["High"].iloc[i]
            curr_c = last_12["Close"].iloc[i]
            if prev_c > 0:
                surge_high = ((curr_h - prev_c) / prev_c) * 100
                surge_close = ((curr_c - prev_c) / prev_c) * 100
                best_surge = max(surge_high, surge_close)
                if best_surge > max_surge:
                    max_surge = best_surge
                if best_surge >= 20.0:
                    surge_detected = True

        if not surge_detected:
            return None

        # 52-Week High
        high_52w = float(df_month["High"].tail(12).max())
        ath = float(df_month["High"].max())
        dist_52w = round(((high_52w - ltp) / high_52w) * 100, 1) if high_52w > 0 else 0.0
        dist_ath = round(((ath - ltp) / ath) * 100, 1) if ath > 0 else 0.0

        # Wick %
        c_open = float(opens.iloc[-1])
        c_close = ltp
        c_low = float(lows.iloc[-1])
        c_high = float(highs.iloc[-1])
        total_range = c_high - c_low
        body_bottom = min(c_open, c_close)
        lower_wick = body_bottom - c_low
        lower_wick_pct = round((lower_wick / total_range) * 100, 1) if total_range > 0 else 0.0

        # Base Months (candles within 10% range of recent high)
        base_months = 1
        for i in range(len(df_month) - 2, max(0, len(df_month) - 7), -1):
            if df_month["Close"].iloc[i] >= curr_ema * 0.95:
                base_months += 1
            else:
                break

        # Setup Classification
        setup_type = "Support on 10 EMA"
        if lower_wick_pct >= 45.0:
            setup_type = "Support Hammer (Lower Wick)"
        elif base_months >= 3:
            setup_type = "Tight Base Consolidation"
        elif dist_52w <= 4.0:
            setup_type = "Near 52W High Breakout"

        is_htf = bool(max_surge >= 85.0 and dist_52w <= 20.0)
        is_ipo = bool(len(df_month) <= 24)

        sec_info = sector_db.get(symbol, {})
        company_name = sec_info.get("name", symbol)
        sector = sec_info.get("sector", "Other")
        sub_sector = sec_info.get("sub_sector", "Other")
        cap = sec_info.get("cap", "Midcap")

        return {
            "Symbol": symbol,
            "Company_Name": company_name,
            "Sector": sector,
            "Sub_Sector": sub_sector,
            "Cap": cap,
            "LTP": round(ltp, 2),
            "Monthly_10EMA": round(curr_ema, 2),
            "Diff_%": diff_pct,
            "High_52W": round(high_52w, 2),
            "Dist_52W_%": dist_52w,
            "ATH": round(ath, 2),
            "Dist_ATH_%": dist_ath,
            "Lower_Wick_%": lower_wick_pct,
            "Base_Months": base_months,
            "Setup_Type": setup_type,
            "Is_IPO": is_ipo,
            "Is_HTF": is_htf,
            "Max_Surge_%": round(max_surge, 1),
            "Last_Updated": datetime.now(IST).isoformat(),
            "Status": "ACTIVE"
        }
    except Exception as e:
        return None

def run_pipeline():
    log("=== Starting NSE Monthly 10-EMA Cloud Scan Pipeline ===")
    sector_db = load_sectors()
    symbols = load_symbols()

    log(f"Loaded {len(symbols)} symbols from master universe.")
    if not symbols:
        log("No symbols to scan. Aborting.")
        return

    # Load existing database to retain if scan is partial
    existing_stocks = {}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                existing_stocks = d.get("stocks", d)
        except Exception:
            pass

    qualified_stocks = {}
    total = len(symbols)
    passed = 0

    log(f"Scanning {total} stocks for Monthly 10-EMA + 20% Momentum...")
    for idx, sym in enumerate(symbols, 1):
        res = scan_symbol(sym, sector_db)
        if res:
            qualified_stocks[sym] = res
            passed += 1

        if idx % 100 == 0 or idx == total:
            log(f"Progress: {idx}/{total} scanned | {passed} qualified so far.")

    log(f"Scan complete. Total qualified stocks: {len(qualified_stocks)}")

    # Fallback to existing if network issue produced 0
    if not qualified_stocks and existing_stocks:
        log("Warning: Scan yielded 0 stocks, keeping existing database.")
        qualified_stocks = existing_stocks

    # Save to screener_database.json
    db_payload = {
        "schema_version": 2,
        "last_scan_time": datetime.now(IST).isoformat(),
        "total_active": len(qualified_stocks),
        "stocks": qualified_stocks
    }
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db_payload, f, ensure_ascii=False, indent=2)
    log(f"Saved {len(qualified_stocks)} stocks to {DB_FILE}")

    # Build Web Terminal (index.html)
    try:
        import build_web_terminal
        build_web_terminal.build()
        log("Web Terminal (index.html) updated successfully.")
    except Exception as e:
        log(f"Error building web terminal: {e}")

    # Send Telegram Alerts if configured
    try:
        import telegram_notifier
        sent = telegram_notifier.send_daily_alerts(max_alerts=10)
        log(f"Telegram notifications sent: {sent}")
    except Exception as e:
        log(f"Error in telegram notifier: {e}")

    log("=== Pipeline Finished Successfully ===")

if __name__ == "__main__":
    run_pipeline()
