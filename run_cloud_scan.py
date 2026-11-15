import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta
import math

IST = timezone(timedelta(hours=5, minutes=30))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

import screener_core

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
            clean = []
            for s in lines:
                s = s.replace(".NS", "")
                if s.endswith("-BE") or s.endswith(".BO") or "NIFTY" in s or "ETF" in s or "GOLD" in s:
                    continue
                clean.append(s)
            return sorted(list(set(clean)))
    return []

def calculate_ema_series(values, period):
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1)
    ema = [sum(values[:period]) / period]
    for v in values[period:]:
        ema.append(v * alpha + ema[-1] * (1.0 - alpha))
    pad = [0.0] * (period - 1)
    return pad + ema

def evaluate_stock_logic(data, sector_db, tol_pct=6.0):
    sym = data["symbol"]
    is_ipo = data["is_ipo"]
    weekly_closes = data.get("weekly_closes", [])
    closes = data["closes"]
    opens = data["opens"]
    highs = data["highs"]
    lows = data["lows"]
    volumes = data["volumes"]

    n = len(closes)
    now_str = datetime.now(IST).isoformat()

    if is_ipo:
        w_n = len(weekly_closes)
        if w_n < 10:
            return None
        w_ema10 = calculate_ema_series(weekly_closes, 10)
        if not w_ema10:
            return None
        e10 = w_ema10[-1]
        c_curr = weekly_closes[-1]
        o_curr = weekly_closes[-1]
        h_curr = max(weekly_closes[-2:])
        l_curr = min(weekly_closes[-2:])
        c_prev = weekly_closes[-2]
        l_prev = min(weekly_closes[-3:])
        e10_prev = w_ema10[-2]
        rule = "IPO Weekly-10EMA Proxy"
    else:
        if n < 10:
            return None
        ema10_series = calculate_ema_series(closes, 10)
        ema20_series = calculate_ema_series(closes, 20) if n >= 20 else []
        ema50_series = calculate_ema_series(closes, 50) if n >= 50 else []

        e10 = ema10_series[-1]
        e20 = ema20_series[-1] if ema20_series else 0.0
        e50 = ema50_series[-1] if ema50_series else 0.0

        if e10 <= 0:
            return None

        # Exact Trend Stack from Main Project
        if n >= 50 and ema20_series and ema50_series:
            trend_ok = (e10 > e20 > e50) and (ema10_series[-1] >= ema10_series[-2])
            rule = "10 > 20 > 50"
        elif n >= 20 and ema20_series:
            trend_ok = (e10 > e20) and (ema10_series[-1] >= ema10_series[-2])
            rule = "10 > 20"
        else:
            trend_ok = (closes[-1] > e10) and (ema10_series[-1] >= ema10_series[-2])
            rule = "Price > 10"

        if not trend_ok:
            return None

        c_curr = closes[-1]
        o_curr = opens[-1]
        h_curr = highs[-1]
        l_curr = lows[-1]

        c_prev = closes[-2]
        l_prev = lows[-2]
        e10_prev = ema10_series[-2]

    diff_pct = ((c_curr - e10) / e10) * 100.0

    high_52w = data["high_52w"]
    ath = data["ath"]

    dist_52w = ((high_52w - c_curr) / high_52w * 100.0) if high_52w > 0 else 0.0
    dist_ath = ((ath - c_curr) / ath * 100.0) if ath > 0 else 0.0

    rng_curr = h_curr - l_curr
    lower_wick_curr = min(o_curr, c_curr) - l_curr
    wick_ratio_curr = (lower_wick_curr / rng_curr * 100.0) if rng_curr > 0 else 0.0

    vol_action = "Normal Volume ⚖️"
    if data.get("provisional"):
        vol_action = "Pending — incomplete month"
    elif len(volumes) >= 4:
        curr_vol = volumes[-1]
        avg_prior_vol = sum(volumes[-4:-1]) / 3.0
        if avg_prior_vol > 0:
            vol_ratio = curr_vol / avg_prior_vol
            if vol_ratio < 0.65:
                vol_action = "Dry-Up Base 💤"
            elif vol_ratio >= 1.25 and c_curr >= o_curr:
                vol_action = "Volume Surge 🚀"
            elif vol_ratio >= 1.25 and c_curr < o_curr:
                vol_action = "High Vol Pullback ⚠️"

    months_base = 0
    if not is_ipo:
        for k in range(1, min(5, n)):
            idx = -k
            if abs((closes[idx] - ema10_series[idx]) / ema10_series[idx]) <= 0.05:
                months_base += 1
            else:
                break

    tested_this_month = (l_curr <= e10 * 1.025) and (c_curr >= e10 * 0.97)
    tested_last_month = (l_prev <= e10_prev * 1.025) and (c_prev >= e10_prev * 0.97)
    bouncing_now = tested_last_month and (c_curr > o_curr) and (c_curr >= e10 * 0.98) and (diff_pct <= 6.0)
    multi_month_base = (months_base >= 2) and (abs(diff_pct) <= 4.0)

    # 12-Month 20%+ Explosive Surge Logic (Exact as Main Project)
    has_20pct_surge = False
    max_surge_pct = 0.0
    lookback = min(12, n - 1)
    for i in range(n - lookback, n):
        c_i = closes[i]
        o_i = opens[i]
        prev_c = closes[i-1]
        ret_co = ((c_i - o_i) / o_i * 100.0) if o_i > 0 else 0.0
        ret_mom = ((c_i - prev_c) / prev_c * 100.0) if prev_c > 0 else 0.0
        m_ret = max(ret_co, ret_mom)
        if m_ret >= 20.0:
            has_20pct_surge = True
            max_surge_pct = max(max_surge_pct, m_ret)

    is_flag = False
    setup_name = None
    if is_ipo:
        if wick_ratio_curr >= 35.0:
            setup_name = "🚀 IPO Hammer (10W EMA Support)"
        elif abs(diff_pct) <= 3.0:
            setup_name = f"🚀 IPO Base ({len(weekly_closes)}W Contraction)"
        elif c_curr > o_curr and diff_pct <= 6.0:
            setup_name = "🚀 IPO Liftoff / Expansion"
        else:
            setup_name = "🚀 IPO Base (Weekly 10 EMA)"
    elif (not is_ipo) and has_20pct_surge and (5.0 < diff_pct <= 15.0) and (dist_52w <= 25.0):
        is_flag = True
        setup_name = f"🚩 High-Tight Flag (+{int(max_surge_pct)}% Move)"
    elif tested_this_month and wick_ratio_curr >= 35.0:
        setup_name = "Support Hammer (Lower Wick)"
    elif bouncing_now:
        setup_name = "Bullish Liftoff / Bounce"
    elif multi_month_base:
        setup_name = f"Tight Base ({months_base}M Contraction)"
    elif tested_this_month and abs(diff_pct) <= tol_pct:
        setup_name = "10 EMA Touch & Hold"

    if setup_name or abs(diff_pct) <= tol_pct or is_flag:
        if not setup_name:
            setup_name = "Near 10 EMA Consolidation"

        sec_meta = sector_db.get(sym, {})
        c_name = sec_meta.get("name", data.get("company_name", sym))
        sec_name = sec_meta.get("sector") or "Diversified Industrials"
        sub_name = sec_meta.get("sub_sector") or "General Industrials"
        cap_val = sec_meta.get("cap") or "Midcap"

        return {
            "Symbol": sym,
            "Data_Status": "Confirmed monthly candle",
            "As_Of": data.get("as_of", now_str[:10]),
            "History_Start": data.get("history_start", ""),
            "High_Basis": "52-week rolling daily / available validated-history high",
            "Data_Quality": data.get("quality_note", ""),
            "Company_Name": c_name,
            "Sector": "ETF / Index Fund" if screener_core.is_etf(sym, c_name) else sec_name,
            "Sub_Sector": "ETF / Index Fund" if screener_core.is_etf(sym, c_name) else sub_name,
            "Cap": "ETF" if screener_core.is_etf(sym, c_name) else cap_val,
            "LTP": round(c_curr, 2),
            "Monthly_10EMA": round(e10, 2),
            "Diff_%": round(diff_pct, 2),
            "High_52W": round(high_52w, 2),
            "Dist_52W_%": round(dist_52w, 1),
            "ATH": round(ath, 2),
            "Dist_ATH_%": round(dist_ath, 1),
            "Lower_Wick_%": round(wick_ratio_curr, 1),
            "Base_Months": int(months_base),
            "Setup_Type": setup_name,
            "Volume_Action": vol_action,
            "Weekly_Trend": "Hold 10W-EMA 🛡️" if is_ipo else "Support on W-20",
            "Trend_Rule": rule,
            "Is_IPO": is_ipo,
            "Is_HTF": is_flag,
            "Max_Surge_%": round(max_surge_pct, 1),
            "Last_Updated": now_str,
            "Status": "ACTIVE"
        }

    return None

def run_pipeline():
    log("=== Starting 100% Main-Project-Aligned Cloud Scan Pipeline ===")
    sector_db = load_sectors()
    symbols = load_symbols()

    log(f"Loaded {len(symbols)} symbols from master list.")
    if not symbols:
        log("No symbols to scan. Aborting.")
        return

    # Reset option support
    force_reset = "--reset" in sys.argv or os.environ.get("FORCE_RESET") == "true"
    existing_stocks = {}
    if force_reset:
        log("FORCE_RESET detected: Wiping existing database and running 100% fresh scan from scratch...")
    elif os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                existing_stocks = d.get("stocks", d)
        except Exception:
            pass

    qualified_stocks = {}
    total = len(symbols)
    passed = 0
    stop_event = lambda: False

    log("Scanning stocks with identical screener_core logic...")
    for idx, sym in enumerate(symbols, 1):
        try:
            hist_res = screener_core.fetch_history(sym, stop_event)
            prep_data = screener_core.prepare_history(sym, hist_res, closed=True)
            res = evaluate_stock_logic(prep_data, sector_db)
            if res:
                qualified_stocks[sym] = res
                passed += 1
        except Exception:
            pass

        if idx % 100 == 0 or idx == total:
            log(f"Progress: {idx}/{total} scanned | {passed} qualified.")

    log(f"Scan complete. Total qualified stocks: {len(qualified_stocks)}")

    if not qualified_stocks and existing_stocks:
        log("Scan returned 0 (network/offline). Preserving existing database.")
        qualified_stocks = existing_stocks

    db_payload = {
        "schema_version": 2,
        "last_scan_time": datetime.now(IST).isoformat(),
        "total_active": len(qualified_stocks),
        "stocks": qualified_stocks
    }
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db_payload, f, ensure_ascii=False, indent=2)

    # Build Web Terminal
    try:
        import build_web_terminal
        build_web_terminal.build()
        log("index.html updated successfully.")
    except Exception as e:
        log(f"Error in web terminal build: {e}")

    # Telegram alerts if configured
    try:
        import telegram_notifier
        telegram_notifier.send_daily_alerts(max_alerts=10)
    except Exception as e:
        log(f"Error in telegram notifier: {e}")

    log("=== Cloud Pipeline Finished Successfully ===")

if __name__ == "__main__":
    run_pipeline()
