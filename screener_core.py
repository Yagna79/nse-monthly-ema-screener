import requests
import http.cookiejar
import xml.etree.ElementTree as ET
import email.utils
"""Data handling independent of Tk; prices use Yahoo quote OHLC consistently."""
import csv
import io
import json
import math
import os
import re
import shutil
import tempfile
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

def is_etf(symbol, name=""):
    """Detects whether a symbol or company represents an ETF/Index Fund rather than an operating equity."""
    s = (symbol or "").upper().strip()
    n = (name or "").upper().strip()

    # Guard genuine listed operating companies
    if s in {"SHANTIGOLD", "SKYGOLD", "GOLDIAM", "GOLDTECH", "CANFINHOME"}:
        return False

    # Name-based signals
    if any(k in n for k in ["EXCHANGE TRADED FUND", " ETF", "BEES", "INDEX FUND"]):
        return True
    if n.endswith("ETF"):
        return True

    # Symbol-based signals
    if s.endswith("BEES") or s.endswith("ETF") or s.endswith("IETF"):
        return True
    if "BEES" in s or "IETF" in s:
        return True

    known_etfs = {
        "GOLD1", "SILVER", "SILVER360", "DECNGOLD", "SBIGOLD", "GROWWGOLD",
        "AONEGOLD", "IVZINGOLD", "HSBCGOLD", "GOLDAXIS", "HDFCGOLD", "GOLDIETF",
        "HDFCBSE500", "HDFCSILVER", "MON100", "MONQ50", "MOLOWVOL", "MASPTOP50",
        "BSLGOLDETF", "PVTBANIETF", "PSUBNKIETF", "PSUBNKBEES", "SILVERBEES", "GOLDBEES"
    }
    return s in known_etfs

def atomic_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    fd, temp = tempfile.mkstemp(dir=directory, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(payload, out, indent=2, ensure_ascii=False, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        if os.path.exists(path):
            shutil.copy2(path, path + '.bak')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def parse_symbols(content):
    content = content.lstrip('\ufeff')
    rows = list(csv.reader(io.StringIO(content)))
    headers = [x.strip().lower() for x in rows[0]] if rows else []
    names = ('symbol', 'ticker', 'tradingsymbol')
    index = next((headers.index(x) for x in names if x in headers), None)
    tokens = ([r[index].strip() for r in rows[1:] if len(r) > index] if index is not None
              else re.split(r'[,;\s]+', content))
    symbols = []
    for token in tokens:
        s = token.strip('"\'').upper()
        if s.startswith('NSE:'):
            s = s[4:]
        if s.endswith('.NS'):
            s = s[:-3]
        # BSE identifiers must not silently become NSE identifiers.
        if s.endswith('.BO') or ':' in s:
            raise ValueError('Only NSE symbols are supported: ' + s)
        if s and re.fullmatch(r'[A-Z0-9][A-Z0-9&_.-]{0,24}', s):
            symbols.append(s)
    return list(dict.fromkeys(symbols))

def fetch_history(symbol, stop, cache_dir=None, max_cache_age_hours=18):
    if cache_dir:
        try:
            cache_file = os.path.join(cache_dir, f"{symbol}.json")
            if os.path.exists(cache_file):
                mtime = os.path.getmtime(cache_file)
                if (time.time() - mtime) < (max_cache_age_hours * 3600):
                    with open(cache_file, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    if cached and "indicators" in cached:
                        return cached
        except Exception:
            pass

    ticker = urllib.parse.quote(symbol + '.NS', safe='')
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=0&period2={int(time.time())}&interval=1d'
    last_error = None
    for attempt in range(3):
        if stop.is_set():
            raise InterruptedError('Scan cancelled')
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as response:
                chart = json.load(response)['chart']
            if chart.get('error') or not chart.get('result'):
                raise ValueError(str(chart.get('error') or 'No data'))
            res = chart['result'][0]
            if cache_dir and res and "indicators" in res:
                try:
                    os.makedirs(cache_dir, exist_ok=True)
                    cache_file = os.path.join(cache_dir, f"{symbol}.json")
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(res, f)
                except Exception:
                    pass
            return res
        except Exception as exc:
            last_error = exc
            if stop.wait(1.5 * (attempt + 1)):
                raise InterruptedError('Scan cancelled')

    # Fallback to older cache if network fails
    if cache_dir:
        try:
            cache_file = os.path.join(cache_dir, f"{symbol}.json")
            if os.path.exists(cache_file):
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if cached and "indicators" in cached:
                    return cached
        except Exception:
            pass

    raise RuntimeError(str(last_error))

def prepare_history(symbol, result, closed=True, now=None):
    now = now or datetime.now(IST)
    quote = result['indicators']['quote'][0]
    adjclose = result.get('indicators', {}).get('adjclose', [{}])[0].get('adjclose', [])
    reg_price = result.get('meta', {}).get('regularMarketPrice')
    bars = []
    skipped_empty = 0
    skipped_invalid_old = 0
    timestamps = result.get('timestamp', [])
    num_bars = len(timestamps)

    for i, timestamp in enumerate(timestamps):
        values = [quote.get(k, [])[i] if i < len(quote.get(k, [])) else None
                  for k in ('open', 'high', 'low', 'close', 'volume')]
        day = datetime.fromtimestamp(timestamp, IST).date()
        if all(v is None for v in values):
            skipped_empty += 1
            continue

        # Yahoo Finance quote data sometimes leaves close as None on latest or unfinalized bars
        if values[3] is None:
            if i < len(adjclose) and adjclose[i] is not None:
                values[3] = adjclose[i]
            elif i == num_bars - 1 and reg_price is not None:
                values[3] = reg_price
            elif values[0] is not None:
                values[3] = values[0]

        # Fill missing open/high/low from available close/open
        if values[0] is None and values[3] is not None:
            values[0] = values[3]
        if values[1] is None and values[3] is not None:
            values[1] = max(values[0] or values[3], values[3])
        if values[2] is None and values[3] is not None:
            values[2] = min(values[0] or values[3], values[3])
        if values[4] is None:
            values[4] = 0.0

        if any(v is None or not math.isfinite(float(v)) for v in values):
            if day < now.date() - timedelta(days=366):
                skipped_invalid_old += 1
                continue
            raise ValueError('Missing or invalid OHLCV data')

        o, h, l, c, v = map(float, values)
        # Accommodate IEEE-754 precision anomalies from JSON float deserialization (e.g. 673.59997 vs 673.6)
        if h < max(o, c) and max(o, c) - h < 0.05:
            h = max(o, c)
        if l > min(o, c) and l - min(o, c) < 0.05:
            l = min(o, c)

        if min(o, h, l, c) <= 0 or l > min(o, c) or h < max(o, c) or v < 0:
            if day < now.date() - timedelta(days=366):
                skipped_invalid_old += 1
                continue
            raise ValueError('Invalid price or volume range')
        bars.append((day, o, h, l, c, v))
    bars.sort(key=lambda b: b[0])
    if not bars:
        raise ValueError('No daily bars')
    if (now.date() - bars[-1][0]).days > 7:
        raise ValueError('Stale price history: ' + str(bars[-1][0]))
    cutoff = now.date().replace(day=1)
    selected = [b for b in bars if not closed or b[0] < cutoff]
    if not selected:
        raise ValueError('No completed monthly candles')
    monthly = {}
    weekly = {}
    for day, o, h, l, c, v in selected:
        key = (day.year, day.month)
        if key not in monthly:
            monthly[key] = [o, h, l, c, v]
        else:
            m = monthly[key]
            m[1], m[2], m[3], m[4] = max(m[1], h), min(m[2], l), c, m[4] + v
        weekly[day - timedelta(days=day.weekday())] = c
    values = list(monthly.values())
    weekly_closes = list(weekly.values())
    is_ipo = len(values) < 10
    if is_ipo:
        if len(weekly_closes) < 8:
            raise ValueError('Insufficient history (New IPO < 8 weeks)')
    asof = selected[-1][0]
    rolling = [b[2] for b in selected if b[0] > asof - timedelta(weeks=52)]
    return dict(symbol=symbol, company_name=result.get('meta', {}).get('longName', symbol),
                opens=[v[0] for v in values], highs=[v[1] for v in values],
                lows=[v[2] for v in values], closes=[v[3] for v in values],
                volumes=[v[4] for v in values], weekly_closes=weekly_closes,
                is_ipo=is_ipo, ipo_months=len(values), ipo_weeks=len(weekly_closes),
                high_52w=max(rolling) if rolling else max(b[2] for b in selected),
                ath=max(b[2] for b in selected),
                quality_note=f'Empty bars skipped: {skipped_empty}; invalid older bars excluded: {skipped_invalid_old}',
                as_of=str(asof), history_start=str(selected[0][0]), provisional=not closed)


def format_crores(raw_val, fmt_str=None):
    if raw_val is not None and isinstance(raw_val, (int, float)) and raw_val != 0:
        cr = raw_val / 10000000.0
        return f"₹{cr:.0f} Cr" if abs(cr) >= 100 else f"₹{cr:.1f} Cr"
    if fmt_str:
        s = str(fmt_str).strip().upper()
        if s.endswith("B"):
            try:
                v = float(s[:-1]) * 100.0
                return f"₹{v:.0f} Cr" if abs(v) >= 100 else f"₹{v:.1f} Cr"
            except:
                pass
        elif s.endswith("M"):
            try:
                v = float(s[:-1]) * 0.1
                return f"₹{v:.1f} Cr"
            except:
                pass
        elif s.endswith("K"):
            try:
                v = float(s[:-1]) * 0.0001
                return f"₹{v:.2f} Cr"
            except:
                pass
    return "N/A"

def parse_screener_number(val_str):
    if not val_str:
        return None
    s = str(val_str).replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except:
        return None

def convert_screener_date_to_quarter(date_str):
    date_str = (date_str or "").strip()
    m = re.match(r'([A-Za-z]+)\s*(\d{4})', date_str)
    if not m:
        return format_quarter_label(date_str)
    month_str = m.group(1)[:3].title()
    year = int(m.group(2))
    
    if month_str in ('Apr', 'May', 'Jun'):
        q_num = 1
        fy_year = year + 1
    elif month_str in ('Jul', 'Aug', 'Sep'):
        q_num = 2
        fy_year = year + 1
    elif month_str in ('Oct', 'Nov', 'Dec'):
        q_num = 3
        fy_year = year + 1
    elif month_str in ('Jan', 'Feb', 'Mar'):
        q_num = 4
        fy_year = year
    else:
        return date_str
        
    return f"Q{q_num} FY{str(fy_year)[2:]} ({month_str} '{str(year)[2:]})"

def format_quarter_label(q_str):
    if not q_str or q_str == "N/A":
        return "Latest Q"
    m = re.match(r'([1-4])Q(\d{4})', q_str)
    if m:
        return f"Q{m.group(1)} FY{m.group(2)[2:]}"
    return q_str

def parse_pct_val(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val * 100.0 if abs(val) < 1.0 else float(val)
    s = str(val).replace("%", "").strip()
    try:
        return float(s)
    except:
        return None

class IntelligenceProvider:
    """Provides Financial Results, Upcoming Earnings Risk, and 3-Day Auto-Expiring Catalyst News."""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.crumb = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.board_meetings = {}
        self.cache = {}
        self.cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intelligence_cache.json")
        self._load_cache()
        self._init_session()
        self._fetch_nse_board_meetings()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except:
                self.cache = {}

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except:
            pass

    def _init_session(self):
        try:
            req = urllib.request.Request("https://fc.yahoo.com", headers=self.headers)
            self.opener.open(req, timeout=4)
        except:
            pass
        try:
            req = urllib.request.Request("https://query1.finance.yahoo.com/v1/test/getcrumb", headers=self.headers)
            with self.opener.open(req, timeout=4) as resp:
                self.crumb = resp.read().decode('utf-8').strip()
        except:
            pass

    def _fetch_nse_board_meetings(self):
        url = "https://www.nseindia.com/api/corporate-board-meetings?index=equities"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.headers["User-Agent"], "Accept": "*/*", "Referer": "https://www.nseindia.com/"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.load(resp)
                now_date = datetime.now(IST).date()
                for item in data:
                    sym = item.get("bm_symbol", "").upper().strip()
                    purpose = item.get("bm_purpose", "")
                    dt_str = item.get("bm_date", "")
                    if sym and dt_str and any(k in purpose.lower() for k in ["financial result", "quarterly", "accounts", "audited"]):
                        try:
                            bm_date = datetime.strptime(dt_str, "%d-%b-%Y").date()
                            days_diff = (bm_date - now_date).days
                            if days_diff >= 0:
                                self.board_meetings[sym] = {
                                    "date_str": dt_str,
                                    "days": days_diff,
                                    "purpose": purpose
                                }
                        except:
                            pass
        except:
            pass

    def analyze_news_sentiment(self, title):
        t = title.lower()
        good_words = ["order win", "bags order", "secures contract", "profit surges", "profit jumps", 
                      "revenue up", "expansion", "dividend", "bonus", "targets", "buy rating", 
                      "soars", "rallies", "partnership", "acquisition", "record high", "multibagger", "growth", "strong q"]
        bad_words = ["crash", "falls", "plunges", "slumps", "fraud", "penalty", "sebi", "raid", 
                     "resigns", "resignation", "warning", "woes", "loss", "margin drop", 
                     "downgrade", "sell rating", "usfda", "pledge", "default", "scam"]
        
        has_good = any(w in t for w in good_words)
        has_bad = any(w in t for w in bad_words)
        
        if has_good and not has_bad:
            return "🟢 Bullish Catalyst"
        elif has_bad and not has_good:
            return "🔴 Bearish Warning"
        elif has_good and has_bad:
            return "🟡 Mixed Signal"
        return "⚪ Neutral / Info"

    def _fetch_screener_in_financials(self, symbol):
        """Fetches up-to-date Indian quarterly fundamentals directly from Screener.in with robust error handling."""
        sym = (symbol or "").upper().replace(".NS", "").replace(".BO", "").strip()
        if not sym:
            return None
        url = f"https://www.screener.in/company/{sym}/"
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200:
                # Try consolidated if standalone returned 404
                resp = self.session.get(f"https://www.screener.in/company/{sym}/consolidated/", timeout=10)
                if resp.status_code != 200:
                    return None
            html = resp.text
        except Exception:
            return None

        try:
            res = {}
            # 1. Parse Top Ratios
            m_ratios = re.search(r'<ul id="top-ratios".*?</ul>', html, re.DOTALL)
            if m_ratios:
                items = re.findall(r'<li[^>]*>(.*?)</li>', m_ratios.group(0), re.DOTALL)
                for item in items:
                    nm = re.search(r'<span class="name">\s*(.*?)\s*</span>', item, re.DOTALL)
                    vm = re.search(r'<span class="nowrap value">\s*(.*?)\s*</span>', item, re.DOTALL)
                    if nm and vm:
                        name = re.sub(r'<[^>]+>', '', nm.group(1)).strip().lower()
                        val = re.sub(r'<[^>]+>', '', vm.group(1)).strip()
                        val_clean = re.sub(r'[^\d\.\-]', '', val)
                        if "roce" in name:
                            res["roce"] = f"{val_clean}%"
                        elif "roe" in name:
                            res["roe"] = f"{val_clean}%"
                        elif "stock p/e" in name or "pe" in name:
                            res["pe"] = val_clean
                        elif "market cap" in name:
                            res["market_cap_cr"] = f"₹{val_clean} Cr"

            # 2. Parse Quarters Table
            m_q = re.search(r'<section id="quarters".*?</section>', html, re.DOTALL)
            if not m_q:
                return None
            sec = m_q.group(0)

            # Quarters Header
            th_matches = re.findall(r'<th[^>]*>(.*?)</th>', sec, re.DOTALL)
            headers = [re.sub(r'<[^>]+>', '', th).strip() for th in th_matches if th.strip()]
            quarter_names = [h for h in headers if re.search(r'[A-Za-z]+\s*\d{4}', h)]
            if not quarter_names:
                return None

            row_data = {}
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', sec, re.DOTALL)
            for r in rows:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.DOTALL)
                clean_tds = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
                if len(clean_tds) > 1:
                    key = clean_tds[0].replace("&nbsp;", " ").replace("+", "").strip().lower()
                    row_data[key] = clean_tds[1:]

            raw_q = quarter_names[-1]
            q_label = convert_screener_date_to_quarter(raw_q)

            sales_row = next((v for k, v in row_data.items() if "sales" in k or "revenue" in k), None)
            pat_row = next((v for k, v in row_data.items() if "net profit" in k), None)
            opm_row = next((v for k, v in row_data.items() if "opm" in k), None)

            rev_val = parse_screener_number(sales_row[-1]) if sales_row and len(sales_row) >= 1 else None
            pat_val = parse_screener_number(pat_row[-1]) if pat_row and len(pat_row) >= 1 else None
            opm_str = opm_row[-1] if opm_row and len(opm_row) >= 1 else "N/A"

            if rev_val is None and pat_val is None:
                return None

            # 4 quarters back = YoY
            rg_val = None
            pg_val = None
            if sales_row and len(sales_row) >= 5:
                prev_sales = parse_screener_number(sales_row[-5])
                if rev_val is not None and prev_sales and prev_sales > 0:
                    rg_val = ((rev_val - prev_sales) / prev_sales) * 100.0

            if pat_row and len(pat_row) >= 5:
                prev_pat = parse_screener_number(pat_row[-5])
                if pat_val is not None and prev_pat and prev_pat != 0:
                    pg_val = ((pat_val - prev_pat) / abs(prev_pat)) * 100.0

            rg_fmt = f"▲ +{rg_val:.1f}%" if rg_val and rg_val > 0 else (f"▼ {rg_val:.1f}%" if rg_val else "N/A")
            pg_fmt = f"▲ +{pg_val:.1f}%" if pg_val and pg_val > 0 else (f"▼ {pg_val:.1f}%" if pg_val else "N/A")

            # Institutional Quality Badge
            if (rg_val and rg_val >= 20.0) and (pg_val and pg_val >= 25.0):
                badge = "🚀 Super Growth"
            elif (rg_val and rg_val > 10.0) or (pg_val and pg_val > 15.0):
                badge = "📈 High Growth"
            elif (rg_val and rg_val > 0) and (pg_val and pg_val > 0):
                badge = "✓ Steady Growth"
            elif pg_val and pg_val > 0 and (rg_val is None or rg_val <= 0):
                badge = "⚡ Turnaround"
            elif rg_val and rg_val > 0 and pg_val and pg_val < 0:
                badge = "⚠️ Margin Squeeze"
            elif rg_val and rg_val < 0 and pg_val and pg_val < 0:
                badge = "🔻 De-growth"
            else:
                badge = "📊 Stable"

            roe_str = res.get("roe", "N/A")
            roce_str = res.get("roce", "N/A")

            return {
                "source": "Screener.in",
                "quarter": raw_q,
                "quarter_label": q_label,
                "revenue": f"{int(rev_val):,} Cr" if rev_val is not None else "N/A",
                "revenue_cr": f"₹{int(rev_val):,} Cr" if rev_val is not None else "N/A",
                "pat": f"{int(pat_val):,} Cr" if pat_val is not None else "N/A",
                "pat_cr": f"₹{int(pat_val):,} Cr" if pat_val is not None else "N/A",
                "rev_growth": f"{rg_val:.1f}%" if rg_val is not None else "N/A",
                "rev_growth_fmt": rg_fmt,
                "pat_growth": f"{pg_val:.1f}%" if pg_val is not None else "N/A",
                "pat_growth_fmt": pg_fmt,
                "profit_margin": opm_str if "%" in opm_str else f"{opm_str}%",
                "profit_margin_fmt": opm_str if "%" in opm_str else f"{opm_str}%",
                "roe": roe_str,
                "roe_fmt": roe_str,
                "roce": roce_str,
                "roce_fmt": roce_str,
                "pe": res.get("pe", "N/A"),
                "badge": badge
            }
        except Exception:
            return None

    def get_stock_intelligence(self, symbol, company_name=""):
        sym = (symbol or "").upper().strip()
        now_ts = time.time()

        # Check Cache (valid for 3 hours)
        cached = self.cache.get(sym)
        if cached and (now_ts - cached.get("_cached_at", 0)) < 10800:
            # Recompute remaining hours on news
            news = cached.get("latest_news")
            if news and news.get("pub_ts"):
                hours_ago = (now_ts - news["pub_ts"]) / 3600.0
                if hours_ago > 72.0:
                    cached["latest_news"] = None
                else:
                    remain_hours = int(72.0 - hours_ago)
                    news["expires_str"] = f"expires in {remain_hours}h"
            return cached

        data = {
            "symbol": sym,
            "_cached_at": now_ts,
            "financials": {},
            "upcoming_earnings": {},
            "latest_news": None
        }

        # 1. Upcoming Earnings Check (NSE Board Meetings first)
        if sym in self.board_meetings:
            bm = self.board_meetings[sym]
            days = bm["days"]
            if days <= 10:
                data["upcoming_earnings"] = {
                    "alert": True,
                    "date": bm["date_str"],
                    "days": days,
                    "badge": f"⚠️ Result in {days}D ({bm['date_str']})",
                    "text": f"🚨 EARNINGS EVENT WARNING: Board Meeting in {days} days ({bm['date_str']}) for Results!"
                }
            else:
                data["upcoming_earnings"] = {
                    "alert": False,
                    "date": bm["date_str"],
                    "days": days,
                    "badge": f"📅 Result {bm['date_str']}",
                    "text": f"✅ Board meeting on {bm['date_str']} ({days} days away)"
                }

        # 2. Financials: Screener.in First (Indian Gold Standard), fallback to Yahoo Finance
        screener_fin = self._fetch_screener_in_financials(sym)
        if screener_fin:
            data["financials"] = screener_fin

        # Check Yahoo Finance if Screener.in didn't produce financials OR to get upcoming earnings calendar
        need_yahoo_fin = False  # Strictly NO Yahoo Finance data for financials, ONLY Screener.in
        need_yahoo_cal = not data["upcoming_earnings"]

        if (need_yahoo_fin or need_yahoo_cal):
            if not self.crumb:
                self._init_session()

            if self.crumb:
                url_y = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}.NS?crumb={self.crumb}&modules=financialData,defaultKeyStatistics,earnings,calendarEvents"
                try:
                    req = urllib.request.Request(url_y, headers=self.headers)
                    with self.opener.open(req, timeout=5) as resp:
                        res = json.load(resp)["quoteSummary"]["result"][0]
                        fin = res.get("financialData", {})
                        earn = res.get("earnings", {})
                        cal = res.get("calendarEvents", {})
                        
                        if need_yahoo_fin:
                            q_list = earn.get("financialsChart", {}).get("quarterly", [])
                            last_q = q_list[-1] if q_list else {}
                            raw_q_name = last_q.get("date", "N/A")
                            q_label = format_quarter_label(raw_q_name)

                            # Look for latest non-zero revenue
                            rev_raw = None
                            rev_fmt = None
                            for q in reversed(q_list):
                                r_raw = q.get("revenue", {}).get("raw")
                                if r_raw and r_raw > 0:
                                    rev_raw = r_raw
                                    rev_fmt = q.get("revenue", {}).get("fmt")
                                    break

                            # Look for latest non-zero net profit
                            pat_raw = None
                            pat_fmt = None
                            for q in reversed(q_list):
                                e_raw = q.get("earnings", {}).get("raw")
                                if e_raw and e_raw != 0:
                                    pat_raw = e_raw
                                    pat_fmt = q.get("earnings", {}).get("fmt")
                                    break

                            margin_raw = fin.get("profitMargins", {}).get("raw")
                            margin_fmt = fin.get("profitMargins", {}).get("fmt", "N/A")

                            # Fallback derived net profit if direct PAT is null but margin and revenue exist
                            if pat_raw is None and rev_raw and margin_raw:
                                pat_raw = rev_raw * margin_raw

                            rev_cr = format_crores(rev_raw, rev_fmt)
                            pat_cr = format_crores(pat_raw, pat_fmt)

                            rg_val = parse_pct_val(fin.get("revenueGrowth", {}).get("raw") or fin.get("revenueGrowth", {}).get("fmt"))
                            pg_val = parse_pct_val(fin.get("earningsGrowth", {}).get("raw") or fin.get("earningsGrowth", {}).get("fmt"))

                            rg_fmt = f"▲ +{rg_val:.1f}%" if rg_val and rg_val > 0 else (f"▼ {rg_val:.1f}%" if rg_val else "N/A")
                            pg_fmt = f"▲ +{pg_val:.1f}%" if pg_val and pg_val > 0 else (f"▼ {pg_val:.1f}%" if pg_val else "N/A")

                            # Institutional Quality Badge
                            if (rg_val and rg_val >= 15.0) and (pg_val and pg_val >= 20.0):
                                badge = "🚀 Super Growth"
                            elif (rg_val and rg_val > 10.0) or (pg_val and pg_val > 15.0):
                                badge = "📈 High Growth"
                            elif (rg_val and rg_val > 0) and (pg_val and pg_val > 0):
                                badge = "✓ Steady Growth"
                            elif pg_val and pg_val > 0 and (rg_val is None or rg_val <= 0):
                                badge = "⚡ Turnaround"
                            elif rg_val and rg_val > 0 and pg_val and pg_val < 0:
                                badge = "⚠️ Margin Squeeze"
                            elif rg_val and rg_val < 0 and pg_val and pg_val < 0:
                                badge = "🔻 De-growth"
                            else:
                                badge = "📊 Stable"

                            roe_fmt = fin.get("returnOnEquity", {}).get("fmt", "N/A")

                            data["financials"] = {
                                "source": "Yahoo Finance",
                                "quarter": raw_q_name,
                                "quarter_label": q_label,
                                "revenue": rev_fmt or rev_cr,
                                "revenue_cr": rev_cr,
                                "pat": pat_fmt or pat_cr,
                                "pat_cr": pat_cr,
                                "rev_growth": fin.get("revenueGrowth", {}).get("fmt", "N/A"),
                                "rev_growth_fmt": rg_fmt,
                                "pat_growth": fin.get("earningsGrowth", {}).get("fmt", "N/A"),
                                "pat_growth_fmt": pg_fmt,
                                "profit_margin": margin_fmt,
                                "profit_margin_fmt": margin_fmt,
                                "roe": roe_fmt,
                                "roe_fmt": roe_fmt,
                                "badge": badge
                            }
                            
                        # If NSE didn't have upcoming date, check Yahoo calendar
                        if not data["upcoming_earnings"]:
                            earn_dates = cal.get("earnings", {}).get("earningsDate", [])
                            if earn_dates:
                                e_str = earn_dates[0].get("fmt")
                                try:
                                    e_date = datetime.strptime(e_str, "%Y-%m-%d").date()
                                    diff = (e_date - datetime.now(IST).date()).days
                                    if 0 <= diff <= 10:
                                        data["upcoming_earnings"] = {
                                            "alert": True, "date": e_str, "days": diff,
                                            "badge": f"⚠️ Result in {diff}D ({e_str})",
                                            "text": f"🚨 EARNINGS EVENT WARNING: Results due in {diff} days ({e_str})!"
                                        }
                                    else:
                                        data["upcoming_earnings"] = {
                                            "alert": False, "date": e_str, "days": diff,
                                            "badge": "✅ Safe",
                                            "text": f"✅ Next Result scheduled on {e_str} (Safe - No near-term event risk)"
                                        }
                                except:
                                    pass
                except:
                    pass

        if not data["upcoming_earnings"]:
            data["upcoming_earnings"] = {"alert": False, "badge": "✅ Safe", "text": "✅ No near-term earnings announcement detected"}

        # 3. Google News RSS with 3-Day (72h) Auto-Expiry
        try:
            now_dt = datetime.now(timezone.utc)
            q_term = urllib.parse.quote(f"{sym} stock OR share")
            url_g = f"https://news.google.com/rss/search?q={q_term}&hl=en-IN&gl=IN&ceid=IN:en"
            req_g = urllib.request.Request(url_g, headers=self.headers)
            with urllib.request.urlopen(req_g, timeout=5) as resp:
                tree = ET.fromstring(resp.read())
                items = tree.findall(".//item")
                for item in items:
                    title = item.find("title").text if item.find("title") is not None else ""
                    pub = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    pub_dt = email.utils.parsedate_to_datetime(pub) if pub else None
                    if pub_dt:
                        diff_hours = (now_dt - pub_dt).total_seconds() / 3600.0
                        # Auto-expiry: strictly within 3 days (72 hours)
                        if diff_hours <= 72.0:
                            sentiment = self.analyze_news_sentiment(title)
                            time_str = f"{int(diff_hours)}h ago" if diff_hours < 24 else f"{int(diff_hours/24)}d ago"
                            remain_hours = int(72.0 - diff_hours)
                            data["latest_news"] = {
                                "title": title,
                                "sentiment": sentiment,
                                "time_str": time_str,
                                "pub_ts": pub_dt.timestamp(),
                                "expires_str": f"expires in {remain_hours}h",
                                "active": True
                            }
                            break
        except:
            pass

        self.cache[sym] = data
        self._save_cache()
        return data

def fetch_stock_intelligence(symbol, company_name=""):
    return IntelligenceProvider.get_instance().get_stock_intelligence(symbol, company_name)
