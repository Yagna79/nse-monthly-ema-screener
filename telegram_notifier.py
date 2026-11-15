import os
import json
import requests
import sys

def load_telegram_credentials():
    # 1. Environment variables (GitHub Actions secrets or system env)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    # 2. Local config file fallback (if testing on desktop)
    config_path = os.path.join(os.path.dirname(__file__), "telegram_config.json")
    if (not token or not chat_id) and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                token = cfg.get("bot_token", token).strip()
                chat_id = cfg.get("chat_id", chat_id).strip()
        except Exception as e:
            print(f"[Telegram] Error loading config file: {e}")

    return token, chat_id

def send_telegram_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            return True, "Success"
        else:
            return False, f"HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, str(e)

def format_stock_alert(stock, intel):
    sym = stock.get("Symbol", "")
    ltp = stock.get("LTP", 0)
    ema = stock.get("Monthly_10EMA", 0)
    diff = stock.get("Diff_%", 0)
    setup = stock.get("Setup_Type", "10-EMA Support")
    wick = stock.get("Lower_Wick_%", 0)
    base_m = stock.get("Base_Months", 0)
    sec = stock.get("Sector", "General")
    cap = stock.get("Cap", "")
    
    fin = intel.get("financials", {})
    pat_growth = fin.get("pat_growth_fmt", "N/A")
    rev = fin.get("revenue_cr", "N/A")
    pat = fin.get("pat_cr", "N/A")
    opm = fin.get("profit_margin_fmt", "N/A")
    badge = fin.get("badge", "Bullish")
    
    earn = intel.get("upcoming_earnings", {})
    earn_text = earn.get("badge", "✅ Safe")
    
    diff_sign = "+" if diff > 0 else ""
    
    msg = (
        f"🎯 <b>10-EMA ALERT: {sym}</b> ({cap})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>LTP:</b> ₹{ltp:,.2f} | <b>10-EMA:</b> ₹{ema:,.2f} (<b>{diff_sign}{diff:.2f}%</b>)\n"
        f"📐 <b>Setup:</b> {setup} (Wick: {wick}%, Base: {base_m}M)\n"
        f"🚀 <b>Growth:</b> PAT YoY {pat_growth} | Rev: {rev} | OPM: {opm}\n"
        f"🏷️ <b>Profile:</b> {badge}\n"
        f"📅 <b>Results:</b> {earn_text}\n"
        f"🏢 <b>Sector:</b> {sec}\n"
        f"🔗 <a href='https://in.tradingview.com/chart/?symbol=NSE:{sym}'>Open TradingView Chart</a> | "
        f"<a href='https://www.screener.in/company/{sym}/'>Screener.in</a>\n"
    )
    return msg

def send_daily_alerts(max_alerts=10):
    token, chat_id = load_telegram_credentials()
    if not token or not chat_id:
        print("[Telegram] Token or Chat ID not configured. Skipping notifications.")
        print("[Telegram] Tip: To enable alerts, set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in GitHub Secrets or telegram_config.json")
        return 0

    base_dir = os.path.dirname(__file__)
    db_path = os.path.join(base_dir, "screener_database.json")
    intel_path = os.path.join(base_dir, "intelligence_cache.json")

    if not os.path.exists(db_path):
        print("[Telegram] Database file not found.")
        return 0

    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)
    stocks = list(db.get("stocks", db).values())

    intel = {}
    if os.path.exists(intel_path):
        with open(intel_path, "r", encoding="utf-8") as f:
            intel = json.load(f)

    # Filter sweet zone stocks (-0.5% to +3.5% from 10 EMA)
    sweet_zone = []
    for s in stocks:
        diff = s.get("Diff_%", 99)
        if -0.5 <= diff <= 3.5:
            sym = s.get("Symbol", "")
            stock_intel = intel.get(sym, {})
            # Score priority based on Growth, HTF, and Lower Wick
            score = 0
            badge = stock_intel.get("financials", {}) .get("badge", "")
            pat = stock_intel.get("financials", {}) .get("pat_growth_fmt", "")
            if "Super Growth" in badge or "▲" in pat:
                score += 50
            if s.get("Is_HTF"):
                score += 30
            if s.get("Lower_Wick_%", 0) >= 40:
                score += 20
            if abs(diff) <= 2.0:
                score += 20
            sweet_zone.append((score, s, stock_intel))

    # Sort highest priority first
    sweet_zone.sort(key=lambda x: x[0], reverse=True)
    top_picks = sweet_zone[:max_alerts]

    if not top_picks:
        summary_msg = "ℹ️ <b>NSE Monthly 10-EMA Daily Scan Complete</b>\nUniverse screened: 1,450+ stocks.\nNo new setups entered the prime 0-3% sweet zone today."
        send_telegram_message(token, chat_id, summary_msg)
        return 0

    header_msg = (
        f"🚨 <b>NSE 10-EMA SCANNER: TOP PICKS IN BUY ZONE</b> 🚨\n"
        f"Found <b>{len(top_picks)}</b> high-momentum setups currently testing Monthly 10-EMA Support!\n"
    )
    send_telegram_message(token, chat_id, header_msg)

    sent_count = 0
    for score, stock, st_intel in top_picks:
        msg = format_stock_alert(stock, st_intel)
        ok, res = send_telegram_message(token, chat_id, msg)
        if ok:
            sent_count += 1
            print(f"[Telegram] Sent alert for {stock.get('Symbol')}")
        else:
            print(f"[Telegram] Failed to send {stock.get('Symbol')}: {res}")

    return sent_count

if __name__ == "__main__":
    send_daily_alerts()
