import json
import os
import sys

def build():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    screener_path = os.path.join(base_dir, 'screener_database.json')
    intel_path = os.path.join(base_dir, 'intelligence_cache.json')
    output_path = os.path.join(base_dir, 'index.html')

    with open(screener_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    intel = {}
    if os.path.exists(intel_path):
        with open(intel_path, 'r', encoding='utf-8') as f:
            intel = json.load(f)

    stocks_dict = db.get('stocks', db)
    stocks_list = list(stocks_dict.values())

    # Merge intelligence into each stock
    for stock in stocks_list:
        sym = stock.get('Symbol', '')
        info = intel.get(sym, {})
        stock['intel'] = info

    # Pre-calculate counts for HUD
    total_stocks = len(stocks_list)
    near_ema_count = sum(1 for s in stocks_list if abs(s.get('Diff_%', 99)) <= 4.0 and not s.get('Is_IPO', False))
    super_growth_count = sum(1 for s in stocks_list if 'Super Growth' in s.get('intel', {}).get('financials', {}).get('badge', '') or '▲' in s.get('intel', {}).get('financials', {}).get('pat_growth_fmt', ''))
    near_52w_count = sum(1 for s in stocks_list if abs(s.get('Dist_52W_%', 99)) <= 5.0)
    htf_count = sum(1 for s in stocks_list if s.get('Is_HTF', False))
    ipo_count = sum(1 for s in stocks_list if s.get('Is_IPO', False))
    earnings_alert_count = sum(1 for s in stocks_list if s.get('intel', {}).get('upcoming_earnings', {}).get('alert', False))

    # Calculate Sector Aggregation for Heatmap
    sector_stats = {}
    for s in stocks_list:
        sec = s.get('Sector', 'Other') or 'Other'
        if sec not in sector_stats:
            sector_stats[sec] = {'total': 0, 'near_ema': 0, 'diffs': []}
        sector_stats[sec]['total'] += 1
        diff = s.get('Diff_%', 99)
        if abs(diff) <= 4.0:
            sector_stats[sec]['near_ema'] += 1
            sector_stats[sec]['diffs'].append(diff)

    sector_heatmap_list = []
    for sec, stats in sector_stats.items():
        if stats['total'] >= 3: # Include sectors with meaningful presence
            avg_diff = sum(stats['diffs']) / len(stats['diffs']) if stats['diffs'] else 0
            sector_heatmap_list.append({
                'sector': sec,
                'total': stats['total'],
                'near_ema': stats['near_ema'],
                'avg_diff': round(avg_diff, 2)
            })

    # Sort sectors with most stocks near EMA first
    sector_heatmap_list.sort(key=lambda x: (x['near_ema'], x['total']), reverse=True)

    stocks_json = json.dumps(stocks_list, ensure_ascii=False)
    heatmap_json = json.dumps(sector_heatmap_list, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NSE Monthly 10-EMA & Financial Intelligence Terminal</title>
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- FontAwesome Icons -->
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <!-- Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          fontFamily: {{
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace'],
          }},
          colors: {{
            terminal: {{
              bg: '#070b14',
              card: '#0e1726',
              cardHover: '#131f37',
              border: '#1e293b',
              accent: '#06b6d4',
              emerald: '#10b981',
              amber: '#f59e0b',
              rose: '#f43f5e',
            }}
          }}
        }}
      }}
    }}
  </script>
  <style>
    body {{
      background: radial-gradient(ellipse at 50% -10%, #172554 0%, #070b14 55%, #030712 100%);
      color: #f1f5f9;
      font-family: 'Inter', sans-serif;
      min-height: 100vh;
      width: 100%;
      overflow-x: hidden;
    }}
    .glass-card {{
      background: rgba(15, 23, 42, 0.75);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .glass-card:hover {{
      border-color: rgba(6, 182, 212, 0.35);
      box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
    }}
    .glow-cyan {{
      box-shadow: 0 0 20px -3px rgba(6, 182, 212, 0.35);
    }}
    /* Dynamic full screen table container */
    .table-container {{
      height: calc(100vh - 355px);
      min-height: 480px;
    }}
    /* Sticky header */
    .table-fixed-header thead th {{
      position: sticky;
      top: 0;
      background: #0b1329;
      z-index: 20;
      box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    }}
    /* Custom Scrollbars */
    ::-webkit-scrollbar {{
      width: 8px;
      height: 8px;
    }}
    ::-webkit-scrollbar-track {{
      background: #070b14;
    }}
    ::-webkit-scrollbar-thumb {{
      background: #1e293b;
      border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: #334155;
    }}
    @keyframes pulse-dot {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: 0.4; transform: scale(0.85); }}
    }}
    .pulse-live {{
      animation: pulse-dot 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }}
  </style>
</head>
<body class="p-2 sm:p-4 lg:p-5 text-slate-100 antialiased selection:bg-cyan-500 selection:text-white">

  <!-- FULL-WIDTH APP WRAPPER -->
  <div class="w-full max-w-[98%] 2xl:max-w-[97%] mx-auto space-y-4">

    <!-- TOP NAVIGATION BAR -->
    <header class="glass-card rounded-2xl p-3 sm:p-4 lg:p-5 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3 border border-slate-800">
      <div class="flex items-center gap-3.5">
        <div class="w-11 h-11 sm:w-12 sm:h-12 rounded-xl bg-gradient-to-br from-cyan-500 via-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-cyan-500/25 shrink-0">
          <i class="fa-solid fa-chart-line text-xl sm:text-2xl"></i>
        </div>
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <h1 class="text-lg sm:text-2xl font-black tracking-tight text-white">NSE ALPHA TERMINAL</h1>
            <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <span class="w-2 h-2 rounded-full bg-emerald-400 pulse-live"></span> CLOUD LIVE
            </span>
            <span class="hidden md:inline-block px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800/90 text-cyan-300 border border-slate-700">
              Monthly 10-EMA + Financial Intelligence
            </span>
          </div>
          <p class="text-xs text-slate-400 mt-0.5">
            Institutional Growth & Monthly Pullback Engine • Sector Rotation Heatmap
          </p>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="flex flex-wrap items-center gap-2 w-full lg:w-auto justify-end">
        <button onclick="exportCSV()" class="px-3.5 py-2 rounded-xl bg-slate-800/90 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-slate-200 transition flex items-center gap-2">
          <i class="fa-solid fa-file-arrow-down text-cyan-400"></i> Export CSV
        </button>
        <button onclick="toggleWatchlistFilter()" id="watchlist-toggle-btn" class="px-3.5 py-2 rounded-xl bg-slate-800/90 hover:bg-amber-500/20 border border-slate-700 text-xs font-semibold text-amber-300 transition flex items-center gap-2">
          <i class="fa-solid fa-star text-amber-400"></i> Watchlist (<span id="watchlist-count">0</span>)
        </button>
        <button onclick="forceResetCache()" class="p-2 w-9 h-9 rounded-xl bg-slate-800/90 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-300 transition flex items-center justify-center" title="Refresh">
          <i class="fa-solid fa-rotate-right text-slate-400"></i>
        </button>
      </div>
    </header>

    <!-- KPI HUD ROW (DYNAMIC RESPONSIVE GRID) -->
    <section class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 sm:gap-3">
      <!-- Total Screened -->
      <div onclick="setCategoryFilter('all')" class="glass-card rounded-xl p-3 sm:p-3.5 cursor-pointer hover:border-cyan-500/50 transition">
        <div class="flex items-center justify-between text-slate-400 text-xs mb-1">
          <span>Universe</span>
          <i class="fa-solid fa-cubes text-slate-500"></i>
        </div>
        <div class="text-xl sm:text-2xl font-bold font-mono text-white" id="stat-total">{total_stocks}</div>
        <div class="text-[10px] text-cyan-400 mt-1 flex items-center gap-1 font-medium truncate">
          <i class="fa-solid fa-circle-check"></i> High Volume Bullish
        </div>
      </div>

      <!-- Near 10 EMA -->
      <div onclick="setCategoryFilter('near_ema')" class="glass-card rounded-xl p-3 sm:p-3.5 cursor-pointer hover:border-emerald-500/50 transition">
        <div class="flex items-center justify-between text-slate-400 text-xs mb-1">
          <span>10-EMA Zone</span>
          <i class="fa-solid fa-crosshairs text-emerald-400"></i>
        </div>
        <div class="text-xl sm:text-2xl font-bold font-mono text-emerald-400" id="stat-ema">{near_ema_count}</div>
        <div class="text-[10px] text-slate-400 mt-1 font-medium truncate">
          Diff ≤ 4.0% to EMA
        </div>
      </div>

      <!-- Super Growth -->
      <div onclick="setCategoryFilter('super_growth')" class="glass-card rounded-xl p-3 sm:p-3.5 cursor-pointer hover:border-purple-500/50 transition">
        <div class="flex items-center justify-between text-slate-400 text-xs mb-1">
          <span>Super Growth</span>
          <i class="fa-solid fa-rocket text-purple-400"></i>
        </div>
        <div class="text-xl sm:text-2xl font-bold font-mono text-purple-300" id="stat-growth">{super_growth_count}</div>
        <div class="text-[10px] text-purple-400 mt-1 font-medium truncate">
          PAT Growth > 25% YoY
        </div>
      </div>

      <!-- Near 52W High -->
      <div onclick="setCategoryFilter('near_52w')" class="glass-card rounded-xl p-3 sm:p-3.5 cursor-pointer hover:border-amber-500/50 transition">
        <div class="flex items-center justify-between text-slate-400 text-xs mb-1">
          <span>Near 52W High</span>
          <i class="fa-solid fa-bolt text-amber-400"></i>
        </div>
        <div class="text-xl sm:text-2xl font-bold font-mono text-amber-300" id="stat-52w">{near_52w_count}</div>
        <div class="text-[10px] text-slate-400 mt-1 font-medium truncate">
          Within 5% of High
        </div>
      </div>

      <!-- High Tight Flags -->
      <div onclick="setCategoryFilter('htf')" class="glass-card rounded-xl p-3 sm:p-3.5 cursor-pointer hover:border-rose-500/50 transition">
        <div class="flex items-center justify-between text-slate-400 text-xs mb-1">
          <span>High-Tight Flag</span>
          <i class="fa-solid fa-flag text-rose-400"></i>
        </div>
        <div class="text-xl sm:text-2xl font-bold font-mono text-rose-300" id="stat-htf">{htf_count}</div>
        <div class="text-[10px] text-slate-400 mt-1 font-medium truncate">
          Surge ≥ 85-100%
        </div>
      </div>

      <!-- Earnings Radar -->
      <div onclick="setCategoryFilter('earnings_alert')" class="glass-card rounded-xl p-3 sm:p-3.5 cursor-pointer hover:border-cyan-500/50 transition">
        <div class="flex items-center justify-between text-slate-400 text-xs mb-1">
          <span>Results Radar</span>
          <i class="fa-solid fa-calendar-check text-cyan-400"></i>
        </div>
        <div class="text-xl sm:text-2xl font-bold font-mono text-cyan-300" id="stat-earnings">{earnings_alert_count}</div>
        <div class="text-[10px] text-cyan-400 mt-1 font-medium truncate">
          Event Radar Active
        </div>
      </div>
    </section>

    <!-- 🧭 SECTOR ROTATION & MARKET BREADTH HEATMAP BAR -->
    <section class="glass-card rounded-xl p-3 border border-slate-800">
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <i class="fa-solid fa-compass text-cyan-400 text-sm"></i>
          <span class="text-xs font-bold uppercase tracking-wider text-slate-300">Sector Rotation Heatmap</span>
          <span class="text-[10px] text-slate-400 hidden sm:inline">(Click any sector tile to filter table)</span>
        </div>
        <button onclick="clearSectorFilter()" id="clear-sector-btn" class="hidden text-[10px] font-semibold text-rose-400 hover:text-rose-300 bg-rose-500/10 px-2 py-0.5 rounded border border-rose-500/20">
          <i class="fa-solid fa-xmark mr-1"></i> Reset Sector Filter
        </button>
      </div>

      <!-- Sector Pills / Tiles -->
      <div id="sectorHeatmapContainer" class="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none text-xs">
        <!-- Rendered dynamically by JS -->
      </div>
    </section>

    <!-- CONTROLS & SEARCH BAR -->
    <section class="space-y-3">
      <!-- Strategy Filter Tabs -->
      <div class="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none text-xs font-semibold">
        <button onclick="setCategoryFilter('all')" data-tab="all" class="tab-btn px-4 py-2 rounded-xl glass-card text-white border-cyan-500 bg-cyan-950/40 hover:bg-cyan-900/40 transition whitespace-nowrap flex items-center gap-2">
          <i class="fa-solid fa-border-all text-cyan-400"></i> All Stocks ({total_stocks})
        </button>
        <button onclick="setCategoryFilter('near_ema')" data-tab="near_ema" class="tab-btn px-4 py-2 rounded-xl glass-card text-slate-300 hover:text-white transition whitespace-nowrap flex items-center gap-2">
          <i class="fa-solid fa-crosshairs text-emerald-400"></i> 10-EMA Pullbacks ({near_ema_count})
        </button>
        <button onclick="setCategoryFilter('super_growth')" data-tab="super_growth" class="tab-btn px-4 py-2 rounded-xl glass-card text-slate-300 hover:text-white transition whitespace-nowrap flex items-center gap-2">
          <i class="fa-solid fa-rocket text-purple-400"></i> Super Growth ({super_growth_count})
        </button>
        <button onclick="setCategoryFilter('htf')" data-tab="htf" class="tab-btn px-4 py-2 rounded-xl glass-card text-slate-300 hover:text-white transition whitespace-nowrap flex items-center gap-2">
          <i class="fa-solid fa-flag text-rose-400"></i> High-Tight Flag ({htf_count})
        </button>
        <button onclick="setCategoryFilter('ipo')" data-tab="ipo" class="tab-btn px-4 py-2 rounded-xl glass-card text-slate-300 hover:text-white transition whitespace-nowrap flex items-center gap-2">
          <i class="fa-solid fa-seedling text-teal-400"></i> Fresh IPOs ({ipo_count})
        </button>
        <button onclick="setCategoryFilter('near_52w')" data-tab="near_52w" class="tab-btn px-4 py-2 rounded-xl glass-card text-slate-300 hover:text-white transition whitespace-nowrap flex items-center gap-2">
          <i class="fa-solid fa-bolt text-amber-400"></i> 52W High Breakouts ({near_52w_count})
        </button>
        <button onclick="setCategoryFilter('earnings_alert')" data-tab="earnings_alert" class="tab-btn px-4 py-2 rounded-xl glass-card text-slate-300 hover:text-white transition whitespace-nowrap flex items-center gap-2">
          <i class="fa-solid fa-bullhorn text-cyan-400"></i> Earnings Radar
        </button>
      </div>

      <!-- Search + Market Cap Pill Selector + Sorter -->
      <div class="glass-card rounded-xl p-2.5 sm:p-3 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
        <!-- Search Input -->
        <div class="relative flex-1">
          <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-xs"></i>
          <input type="text" id="searchInput" oninput="applyFilters()" placeholder="Search symbol, company name, or sector (e.g. GRWRHITECH, Tata, IT, Pharma)..."
            class="w-full pl-10 pr-16 py-2 bg-slate-900/90 border border-slate-700/80 rounded-lg text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition">
          <span class="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">Ctrl + K</span>
        </div>

        <!-- Cap Filters -->
        <div class="flex items-center gap-1.5 overflow-x-auto text-xs">
          <span class="text-slate-400 text-[11px] font-medium mr-1"><i class="fa-solid fa-filter"></i> Cap:</span>
          <button onclick="setCapFilter('ALL')" data-cap="ALL" class="cap-btn px-3 py-1 rounded-md bg-cyan-500 text-slate-950 font-bold transition">All</button>
          <button onclick="setCapFilter('Largecap')" data-cap="Largecap" class="cap-btn px-3 py-1 rounded-md bg-slate-800 text-slate-300 hover:bg-slate-700 transition">Large</button>
          <button onclick="setCapFilter('Midcap')" data-cap="Midcap" class="cap-btn px-3 py-1 rounded-md bg-slate-800 text-slate-300 hover:bg-slate-700 transition">Mid</button>
          <button onclick="setCapFilter('Smallcap')" data-cap="Smallcap" class="cap-btn px-3 py-1 rounded-md bg-slate-800 text-slate-300 hover:bg-slate-700 transition">Small</button>
          <button onclick="setCapFilter('Microcap')" data-cap="Microcap" class="cap-btn px-3 py-1 rounded-md bg-slate-800 text-slate-300 hover:bg-slate-700 transition">Micro</button>
        </div>

        <!-- Sort Dropdown -->
        <div class="flex items-center gap-2 text-xs">
          <span class="text-slate-400 text-[11px] font-medium whitespace-nowrap"><i class="fa-solid fa-arrow-down-short-wide"></i> Sort:</span>
          <select id="sortSelect" onchange="applySorting()" class="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-slate-200 focus:outline-none focus:border-cyan-500">
            <option value="diff_asc">10-EMA Distance (Closest First)</option>
            <option value="pat_desc">YoY PAT Growth (Highest First)</option>
            <option value="dist52_asc">52W High Proximity (Closest First)</option>
            <option value="symbol_asc">Symbol (A-Z)</option>
            <option value="ltp_desc">Price (Highest First)</option>
          </select>
        </div>
      </div>
    </section>

    <!-- MAIN FULL-WIDTH DATA TABLE -->
    <main>
      <div class="glass-card rounded-2xl overflow-hidden border border-slate-800 shadow-2xl">
        <!-- Table Header Summary -->
        <div class="px-4 py-2.5 border-b border-slate-800 flex flex-wrap items-center justify-between text-xs text-slate-400 bg-slate-900/60 gap-2">
          <div class="flex items-center gap-2">
            <span>Showing <span id="filtered-count" class="font-bold font-mono text-cyan-400">{total_stocks}</span> of <span class="font-mono">{total_stocks}</span> stocks</span>
            <span id="active-sector-tag" class="hidden px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"></span>
          </div>
          <div class="text-[11px] flex items-center gap-3">
            <span class="inline-flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-emerald-400"></span> 0-3% Sweet Zone</span>
            <span class="inline-flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-cyan-400"></span> 3-6% Optimal</span>
            <span class="inline-flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-amber-400"></span> >6% Extended</span>
          </div>
        </div>

        <!-- Dynamic Scrollable Table -->
        <div class="overflow-x-auto table-container scrollbar-thin">
          <table class="w-full text-left border-collapse table-fixed-header">
            <thead>
              <tr class="text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-800">
                <th class="py-3 px-3 font-semibold w-12 text-center">#</th>
                <th class="py-3 px-3 font-semibold min-w-[210px]">Stock & Sector</th>
                <th class="py-3 px-3 font-semibold min-w-[130px]">LTP & 10 EMA</th>
                <th class="py-3 px-3 font-semibold min-w-[100px]">EMA Diff</th>
                <th class="py-3 px-3 font-semibold min-w-[140px]">Setup & Wick</th>
                <th class="py-3 px-3 font-semibold min-w-[150px]">52W High Proximity</th>
                <th class="py-3 px-3 font-semibold min-w-[220px]">Financial Intelligence (Qtr)</th>
                <th class="py-3 px-3 font-semibold min-w-[150px]">Catalyst Radar</th>
                <th class="py-3 px-3 font-semibold w-28 text-center">Action</th>
              </tr>
            </thead>
            <tbody id="stockTableBody" class="divide-y divide-slate-800/60 text-xs">
              <!-- Dynamically populated rows -->
            </tbody>
          </table>
        </div>
      </div>
    </main>

  </div>

  <!-- STOCK INSPECTOR MODAL (DEEP DIVE DRAWER) -->
  <div id="inspectorModal" class="fixed inset-0 z-50 hidden flex items-center justify-center p-3 md:p-6 bg-slate-950/80 backdrop-blur-md transition-opacity">
    <div class="glass-card rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto border border-cyan-500/30 p-5 md:p-7 shadow-2xl relative">
      <!-- Close button -->
      <button onclick="closeInspector()" class="absolute top-5 right-5 w-8 h-8 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition">
        <i class="fa-solid fa-xmark"></i>
      </button>

      <!-- Modal Content (Rendered by JS) -->
      <div id="modalBody"></div>
    </div>
  </div>

  <!-- EMBEDDED REAL DATABASE DATA -->
  <script>
    // Embedded live stock database with merged intelligence
    const STOCKS_DATA = {stocks_json};
    const SECTOR_HEATMAP = {heatmap_json};

    let currentCategory = 'all';
    let currentCap = 'ALL';
    let currentSector = 'ALL';
    let searchQuery = '';
    let watchlistOnly = false;
    let watchlist = JSON.parse(localStorage.getItem('nse_watchlist') || '[]');

    // Initialize on load
    document.addEventListener('DOMContentLoaded', () => {{
      renderSectorHeatmap();
      updateWatchlistCount();
      applyFilters();

      // Keyboard shortcut for search
      window.addEventListener('keydown', (e) => {{
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {{
          e.preventDefault();
          document.getElementById('searchInput').focus();
        }}
        if (e.key === 'Escape') {{
          closeInspector();
        }}
      }});
    }});

    function renderSectorHeatmap() {{
      const container = document.getElementById('sectorHeatmapContainer');
      if (!container) return;

      let html = '';
      SECTOR_HEATMAP.forEach(item => {{
        const isSelected = currentSector.toLowerCase() === item.sector.toLowerCase();
        const borderStyle = isSelected ? 'border-cyan-400 bg-cyan-950/50' : 'border-slate-800 bg-slate-900/60 hover:border-slate-700';
        
        html += `
          <div onclick="filterBySector('${{item.sector.replace(/'/g, "\\\\'")}}')" 
            class="sector-tile flex-shrink-0 cursor-pointer p-2 rounded-lg border ${{borderStyle}} transition flex items-center gap-2">
            <div>
              <div class="font-bold text-slate-200 text-xs">${{item.sector}}</div>
              <div class="text-[10px] text-slate-400 mt-0.5 flex items-center gap-1.5">
                <span class="text-emerald-400 font-semibold">${{item.near_ema}} in Zone</span>
                <span>•</span>
                <span>${{item.total}} Total</span>
              </div>
            </div>
          </div>
        `;
      }});

      container.innerHTML = html;
    }}

    function filterBySector(sector) {{
      if (currentSector.toLowerCase() === sector.toLowerCase()) {{
        clearSectorFilter();
        return;
      }}
      currentSector = sector;
      document.getElementById('clear-sector-btn').classList.remove('hidden');
      const tag = document.getElementById('active-sector-tag');
      tag.classList.remove('hidden');
      tag.innerText = `Sector: ${{sector}}`;
      renderSectorHeatmap();
      applyFilters();
    }}

    function clearSectorFilter() {{
      currentSector = 'ALL';
      document.getElementById('clear-sector-btn').classList.add('hidden');
      document.getElementById('active-sector-tag').classList.add('hidden');
      renderSectorHeatmap();
      applyFilters();
    }}

    function updateWatchlistCount() {{
      const el = document.getElementById('watchlist-count');
      if (el) el.innerText = watchlist.length;
    }}

    function toggleWatchlist(symbol, event) {{
      if (event) event.stopPropagation();
      const idx = watchlist.indexOf(symbol);
      if (idx > -1) {{
        watchlist.splice(idx, 1);
      }} else {{
        watchlist.push(symbol);
      }}
      localStorage.setItem('nse_watchlist', JSON.stringify(watchlist));
      updateWatchlistCount();
      applyFilters();
      if (!document.getElementById('inspectorModal').classList.contains('hidden')) {{
        const curSym = document.getElementById('modal-symbol')?.innerText;
        if (curSym === symbol) {{
          updateModalWatchlistBtn(symbol);
        }}
      }}
    }}

    function toggleWatchlistFilter() {{
      watchlistOnly = !watchlistOnly;
      const btn = document.getElementById('watchlist-toggle-btn');
      if (watchlistOnly) {{
        btn.classList.add('bg-amber-500/30', 'border-amber-400');
      }} else {{
        btn.classList.remove('bg-amber-500/30', 'border-amber-400');
      }}
      applyFilters();
    }}

    function setCategoryFilter(cat) {{
      currentCategory = cat;
      document.querySelectorAll('.tab-btn').forEach(btn => {{
        if (btn.getAttribute('data-tab') === cat) {{
          btn.classList.add('border-cyan-500', 'bg-cyan-950/40', 'text-white');
          btn.classList.remove('text-slate-300');
        }} else {{
          btn.classList.remove('border-cyan-500', 'bg-cyan-950/40', 'text-white');
          btn.classList.add('text-slate-300');
        }}
      }});
      applyFilters();
    }}

    function setCapFilter(cap) {{
      currentCap = cap;
      document.querySelectorAll('.cap-btn').forEach(btn => {{
        if (btn.getAttribute('data-cap') === cap) {{
          btn.classList.add('bg-cyan-500', 'text-slate-950', 'font-bold');
          btn.classList.remove('bg-slate-800', 'text-slate-300');
        }} else {{
          btn.classList.remove('bg-cyan-500', 'text-slate-950', 'font-bold');
          btn.classList.add('bg-slate-800', 'text-slate-300');
        }}
      }});
      applyFilters();
    }}

    function forceResetCache() {{
      const url = new URL(window.location.href);
      url.searchParams.set('t', Date.now());
      window.location.href = url.href;
    }}

    function applySorting() {{
      applyFilters();
    }}

    function applyFilters() {{
      const query = document.getElementById('searchInput').value.trim().toLowerCase();
      const sortVal = document.getElementById('sortSelect').value;

      let filtered = STOCKS_DATA.filter(stock => {{
        // Watchlist filter
        if (watchlistOnly && !watchlist.includes(stock.Symbol)) {{
          return false;
        }}

        // Sector Filter from Heatmap
        if (currentSector !== 'ALL') {{
          const sec = (stock.Sector || '').toLowerCase();
          if (sec !== currentSector.toLowerCase()) return false;
        }}

        // Cap filter
        if (currentCap !== 'ALL') {{
          const cap = (stock.Cap || '').toLowerCase();
          if (!cap.includes(currentCap.toLowerCase())) return false;
        }}

        // Category filter
        if (currentCategory === 'near_ema') {{
          if (Math.abs(stock['Diff_%'] || 99) > 4.0) return false;
        }} else if (currentCategory === 'super_growth') {{
          const badge = stock.intel?.financials?.badge || '';
          const pat = stock.intel?.financials?.pat_growth_fmt || '';
          if (!badge.includes('Super Growth') && !pat.includes('▲')) return false;
        }} else if (currentCategory === 'htf') {{
          if (!stock.Is_HTF) return false;
        }} else if (currentCategory === 'ipo') {{
          if (!stock.Is_IPO) return false;
        }} else if (currentCategory === 'near_52w') {{
          if (Math.abs(stock['Dist_52W_%'] || 99) > 5.0) return false;
        }} else if (currentCategory === 'earnings_alert') {{
          if (!stock.intel?.upcoming_earnings?.alert) return false;
        }}

        // Search text
        if (query) {{
          const sym = (stock.Symbol || '').toLowerCase();
          const name = (stock.Company_Name || '').toLowerCase();
          const sec = (stock.Sector || '').toLowerCase();
          const sub = (stock.Sub_Sector || '').toLowerCase();
          if (!sym.includes(query) && !name.includes(query) && !sec.includes(query) && !sub.includes(query)) {{
            return false;
          }}
        }}

        return true;
      }});

      // Apply sorting
      filtered.sort((a, b) => {{
        if (sortVal === 'diff_asc') return (a['Diff_%'] || 0) - (b['Diff_%'] || 0);
        if (sortVal === 'dist52_asc') return (a['Dist_52W_%'] || 0) - (b['Dist_52W_%'] || 0);
        if (sortVal === 'ltp_desc') return (b['LTP'] || 0) - (a['LTP'] || 0);
        if (sortVal === 'symbol_asc') return (a.Symbol || '').localeCompare(b.Symbol || '');
        if (sortVal === 'pat_desc') {{
          const pA = parseFloat((a.intel?.financials?.pat_growth || '0').replace('%', '')) || 0;
          const pB = parseFloat((b.intel?.financials?.pat_growth || '0').replace('%', '')) || 0;
          return pB - pA;
        }}
        return 0;
      }});

      renderTable(filtered);
    }}

    function renderTable(stocks) {{
      const tbody = document.getElementById('stockTableBody');
      const filteredEl = document.getElementById('filtered-count');
      if (filteredEl) filteredEl.innerText = stocks.length;

      if (!tbody) return;

      if (stocks.length === 0) {{
        tbody.innerHTML = `
          <tr>
            <td colspan="9" class="py-12 text-center text-slate-500">
              <i class="fa-solid fa-folder-open text-4xl mb-3 block text-slate-600"></i>
              No stocks found matching the active filter criteria.
            </td>
          </tr>
        `;
        return;
      }}

      let html = '';
      stocks.forEach((stock, idx) => {{
        const isWatched = watchlist.includes(stock.Symbol);
        const diff = stock['Diff_%'] || 0;
        const dist52 = stock['Dist_52W_%'] || 0;
        const wick = stock['Lower_Wick_%'] || 0;
        const baseM = stock.Base_Months || 0;
        const intel = stock.intel || {{}};
        const fin = intel.financials || {{}};
        const earn = intel.upcoming_earnings || {{}};
        const news = intel.latest_news || {{}};

        // Diff badge styling
        let diffBadgeClass = 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30';
        if (diff <= 3.0) diffBadgeClass = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
        else if (diff > 6.0) diffBadgeClass = 'bg-amber-500/15 text-amber-300 border-amber-500/30';

        // Cap badge styling
        let capClass = 'bg-slate-800 text-slate-400 border-slate-700';
        if (stock.Cap === 'Largecap') capClass = 'bg-blue-500/10 text-blue-400 border-blue-500/20';
        else if (stock.Cap === 'Midcap') capClass = 'bg-teal-500/10 text-teal-400 border-teal-500/20';
        else if (stock.Cap === 'Smallcap') capClass = 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20';
        else if (stock.Cap === 'Microcap') capClass = 'bg-purple-500/10 text-purple-400 border-purple-500/20';

        // 52W Progress bar width
        const progWidth = Math.max(5, Math.min(100, 100 - dist52 * 4));

        // Growth tag
        let growthBadgeHtml = '';
        if (fin.badge) {{
          growthBadgeHtml = `<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">${{fin.badge}}</span>`;
        }}

        // Earnings radar badge
        let earnBadgeHtml = `<span class="inline-flex items-center gap-1 text-[10px] text-slate-400"><i class="fa-solid fa-shield-halved text-emerald-400"></i> No Near Event</span>`;
        if (earn.alert) {{
          earnBadgeHtml = `<span class="inline-flex items-center gap-1 text-[10px] font-bold text-amber-300 bg-amber-500/20 px-2 py-0.5 rounded border border-amber-500/40 animate-pulse"><i class="fa-solid fa-triangle-exclamation"></i> Upcoming Result!</span>`;
        }}

        html += `
          <tr class="hover:bg-slate-800/40 transition cursor-pointer group" onclick="openInspector('${{stock.Symbol}}')">
            <!-- Sr & Watchlist -->
            <td class="py-3 px-3 text-center text-slate-500 font-mono text-xs" onclick="event.stopPropagation()">
              <button onclick="toggleWatchlist('${{stock.Symbol}}', event)" class="hover:scale-125 transition text-xs mr-1 text-${{isWatched ? 'amber-400' : 'slate-600 hover:text-amber-400'}}">
                <i class="fa-${{isWatched ? 'solid' : 'regular'}} fa-star"></i>
              </button>
              ${{idx + 1}}
            </td>

            <!-- Stock & Sector -->
            <td class="py-3 px-3">
              <div class="flex items-center gap-2">
                <span class="font-black text-cyan-300 text-sm tracking-wide font-mono group-hover:text-cyan-200 transition">${{stock.Symbol}}</span>
                <span class="px-1.5 py-0.2 rounded text-[10px] font-medium border ${{capClass}}">${{stock.Cap || 'Stock'}}</span>
                ${{stock.Is_IPO ? '<span class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-teal-500/20 text-teal-300 border border-teal-500/30">IPO</span>' : ''}}
                ${{stock.Is_HTF ? '<span class="px-1.5 py-0.2 rounded text-[9px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">HTF</span>' : ''}}
              </div>
              <div class="text-[11px] text-slate-400 truncate max-w-[240px] mt-0.5" title="${{stock.Company_Name || ''}}">
                ${{stock.Company_Name || ''}}
              </div>
              <div class="text-[10px] text-slate-500 truncate max-w-[240px]">
                ${{stock.Sector || 'General'}} • ${{stock.Sub_Sector || ''}}
              </div>
            </td>

            <!-- LTP & 10 EMA -->
            <td class="py-3 px-3 font-mono">
              <div class="font-bold text-slate-100 text-xs">₹${{Number(stock.LTP || 0).toLocaleString('en-IN')}}</div>
              <div class="text-[10px] text-slate-400 flex items-center gap-1">
                <span>EMA:</span> ₹${{Number(stock.Monthly_10EMA || 0).toLocaleString('en-IN')}}
              </div>
            </td>

            <!-- EMA Diff -->
            <td class="py-3 px-3 font-mono">
              <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold border ${{diffBadgeClass}}">
                ${{diff > 0 ? '+' : ''}}${{Number(diff).toFixed(2)}}%
              </span>
            </td>

            <!-- Setup & Wick -->
            <td class="py-3 px-3">
              <div class="text-xs font-semibold text-slate-200 truncate max-w-[150px]">${{stock.Setup_Type || 'Support'}}</div>
              <div class="flex items-center gap-2 mt-1 text-[10px] text-slate-400">
                <span class="bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">Wick: ${{wick}}%</span>
                <span>Base: ${{baseM}}M</span>
              </div>
            </td>

            <!-- 52W High Proximity -->
            <td class="py-3 px-3 font-mono">
              <div class="flex items-center justify-between text-[11px] mb-1">
                <span class="text-slate-400">High: ₹${{Number(stock.High_52W || 0).toLocaleString('en-IN')}}</span>
                <span class="text-amber-400 font-bold">-${{Number(dist52).toFixed(1)}}%</span>
              </div>
              <div class="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                <div class="bg-gradient-to-r from-cyan-500 to-amber-400 h-1.5 rounded-full" style="width: ${{progWidth}}%"></div>
              </div>
            </td>

            <!-- Financial Intelligence -->
            <td class="py-3 px-3">
              <div class="flex items-center gap-2 mb-1">
                ${{growthBadgeHtml}}
                <span class="text-[10px] font-mono text-emerald-400 font-bold">${{fin.pat_growth_fmt || 'PAT: --'}}</span>
              </div>
              <div class="text-[10px] text-slate-400 font-mono flex items-center gap-2">
                <span>Rev: ${{fin.revenue_cr || '--'}}</span>
                <span>•</span>
                <span>PAT: ${{fin.pat_cr || '--'}}</span>
                <span>•</span>
                <span>OPM: ${{fin.profit_margin_fmt || '--'}}</span>
              </div>
            </td>

            <!-- Catalyst Radar -->
            <td class="py-3 px-3">
              <div class="mb-1">${{earnBadgeHtml}}</div>
              <div class="text-[10px] text-slate-400 truncate max-w-[160px]" title="${{news.title || 'No recent headline'}}">
                ${{news.sentiment ? news.sentiment.split(' ')[0] : '⚪'}} ${{news.title || 'Market Update'}}
              </div>
            </td>

            <!-- Actions -->
            <td class="py-3 px-3 text-center" onclick="event.stopPropagation()">
              <div class="flex items-center justify-center gap-1.5">
                <button onclick="openInspector('${{stock.Symbol}}')" class="p-1.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/30 text-cyan-400 border border-cyan-500/20 text-xs transition" title="Inspect Terminal">
                  <i class="fa-solid fa-magnifying-glass-chart"></i>
                </button>
                <a href="https://in.tradingview.com/chart/?symbol=NSE:${{stock.Symbol}}" target="_blank" class="p-1.5 rounded-lg bg-slate-800 hover:bg-blue-600/30 text-blue-400 border border-slate-700 text-xs transition" title="TradingView Chart">
                  <i class="fa-solid fa-arrow-up-right-from-square"></i>
                </a>
                <a href="https://www.screener.in/company/${{stock.Symbol}}/" target="_blank" class="p-1.5 rounded-lg bg-slate-800 hover:bg-emerald-600/30 text-emerald-400 border border-slate-700 text-xs transition" title="Screener.in Financials">
                  <i class="fa-solid fa-file-invoice-dollar"></i>
                </a>
              </div>
            </td>
          </tr>
        `;
      }});

      tbody.innerHTML = html;
    }}

    // MODAL INSPECTOR
    function openInspector(symbol) {{
      const stock = STOCKS_DATA.find(s => s.Symbol === symbol);
      if (!stock) return;

      const intel = stock.intel || {{}};
      const fin = intel.financials || {{}};
      const earn = intel.upcoming_earnings || {{}};
      const news = intel.latest_news || {{}};
      const isWatched = watchlist.includes(stock.Symbol);
      const wick = stock['Lower_Wick_%'] || 0;
      const baseM = stock.Base_Months || 0;

      const modalBody = document.getElementById('modalBody');
      modalBody.innerHTML = `
        <!-- Header -->
        <div class="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-slate-800 gap-3">
          <div>
            <div class="flex items-center gap-3">
              <span id="modal-symbol" class="text-2xl font-black font-mono text-cyan-300 tracking-wider">${{stock.Symbol}}</span>
              <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">${{stock.Cap || 'Stock'}}</span>
              ${{stock.Is_HTF ? '<span class="px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">🔥 High-Tight Flag</span>' : ''}}
              ${{stock.Is_IPO ? '<span class="px-2 py-0.5 rounded-full text-xs font-semibold bg-teal-500/20 text-teal-300 border border-teal-500/30">🐣 Fresh IPO</span>' : ''}}
            </div>
            <div class="text-sm text-slate-300 font-medium mt-1">${{stock.Company_Name || ''}}</div>
            <div class="text-xs text-slate-400 mt-0.5"><i class="fa-solid fa-industry mr-1 text-slate-500"></i>${{stock.Sector || 'General'}} • ${{stock.Sub_Sector || ''}}</div>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="toggleWatchlist('${{stock.Symbol}}')" id="modal-watchlist-btn" class="px-3.5 py-2 rounded-xl text-xs font-bold border transition flex items-center gap-2 ${{isWatched ? 'bg-amber-500 text-slate-950 border-amber-400' : 'bg-slate-800 text-amber-400 border-slate-700 hover:bg-slate-700'}}">
              <i class="fa-${{isWatched ? 'solid' : 'regular'}} fa-star"></i> ${{isWatched ? 'In Watchlist' : 'Add to Watchlist'}}
            </button>
            <a href="https://in.tradingview.com/chart/?symbol=NSE:${{stock.Symbol}}" target="_blank" class="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold transition flex items-center gap-1.5">
              <i class="fa-solid fa-chart-line"></i> Chart
            </a>
            <a href="https://www.screener.in/company/${{stock.Symbol}}/" target="_blank" class="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1.5">
              <i class="fa-solid fa-file-invoice-dollar"></i> Screener.in
            </a>
          </div>
        </div>

        <!-- 4-Card Financial Intelligence Scorecard -->
        <div class="mt-5">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <i class="fa-solid fa-coins text-amber-400"></i> Quarterly Financial Intelligence (${{fin.quarter_label || 'Latest'}})
            </h3>
            <span class="text-[10px] text-slate-500">Source: ${{fin.source || 'NSE / Screener'}}</span>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div class="glass-card rounded-xl p-3 border border-slate-800">
              <div class="text-[11px] text-slate-400">Quarterly Sales (Rev)</div>
              <div class="text-lg font-bold font-mono text-white mt-0.5">${{(fin.revenue_cr && fin.revenue_cr !== 'N/A') ? fin.revenue_cr : (fin.rev_growth_fmt || 'High Sales')}}</div>
              <div class="text-[11px] font-semibold text-emerald-400 mt-1">${{(fin.revenue_cr && fin.revenue_cr !== 'N/A') ? (fin.rev_growth_fmt ? fin.rev_growth_fmt + ' YoY' : 'Sales Growth') : 'YoY Growth'}}</div>
            </div>
            <div class="glass-card rounded-xl p-3 border border-slate-800">
              <div class="text-[11px] text-slate-400">Net Profit (PAT)</div>
              <div class="text-lg font-bold font-mono text-emerald-400 mt-0.5">${{(fin.pat_cr && fin.pat_cr !== 'N/A') ? fin.pat_cr : (fin.pat_growth_fmt || 'Profitable')}}</div>
              <div class="text-[11px] font-semibold text-emerald-400 mt-1">${{(fin.pat_cr && fin.pat_cr !== 'N/A') ? (fin.pat_growth_fmt ? fin.pat_growth_fmt + ' YoY' : 'Net Profit') : 'YoY Expansion'}}</div>
            </div>
            <div class="glass-card rounded-xl p-3 border border-slate-800">
              <div class="text-[11px] text-slate-400">Operating Margin (OPM)</div>
              <div class="text-lg font-bold font-mono text-cyan-300 mt-0.5">${{fin.profit_margin_fmt || '--'}}</div>
              <div class="text-[11px] text-slate-400 mt-1">ROE: ${{fin.roe_fmt || '--'}}</div>
            </div>
            <div class="glass-card rounded-xl p-3 border border-slate-800">
              <div class="text-[11px] text-slate-400">Growth Profile</div>
              <div class="text-sm font-bold text-purple-300 mt-1 truncate">${{fin.badge || '⚡ Active Bull'}}</div>
              <div class="text-[10px] text-slate-400 mt-1">Institutional High Momentum</div>
            </div>
          </div>
        </div>

        <!-- Technical Structure Breakdown -->
        <div class="mt-5">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
            <i class="fa-solid fa-chart-simple text-cyan-400"></i> Technical Momentum Anatomy
          </h3>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div class="glass-card rounded-xl p-3 border border-slate-800">
              <div class="text-[11px] text-slate-400">Current LTP</div>
              <div class="text-base font-bold font-mono text-white mt-0.5">₹${{Number(stock.LTP || 0).toLocaleString('en-IN')}}</div>
              <div class="text-[10px] text-cyan-400 mt-1">10-EMA: ₹${{Number(stock.Monthly_10EMA || 0).toLocaleString('en-IN')}}</div>
            </div>
            <div class="glass-card rounded-xl p-3 border border-slate-800">
              <div class="text-[11px] text-slate-400">10-EMA Distance</div>
              <div class="text-base font-bold font-mono text-emerald-400 mt-0.5">${{stock['Diff_%'] > 0 ? '+' : ''}}${{Number(stock['Diff_%'] || 0).toFixed(2)}}%</div>
              <div class="text-[10px] text-slate-400 mt-1">${{Math.abs(stock['Diff_%'] || 99) <= 3 ? '✅ In Prime Zone' : 'Pullback Setup'}}</div>
            </div>
            <div class="glass-card rounded-xl p-3 border border-slate-800">
              <div class="text-[11px] text-slate-400">52W High / ATH</div>
              <div class="text-base font-bold font-mono text-amber-300 mt-0.5">₹${{Number(stock.High_52W || 0).toLocaleString('en-IN')}}</div>
              <div class="text-[10px] text-slate-400 mt-1">Distance: -${{Number(stock['Dist_52W_%'] || 0).toFixed(1)}}%</div>
            </div>
            <div class="glass-card rounded-xl p-3 border border-slate-800">
              <div class="text-[11px] text-slate-400">Lower Wick Support</div>
              <div class="text-base font-bold font-mono text-teal-300 mt-0.5">${{wick}}%</div>
              <div class="text-[10px] text-slate-400 mt-1">Base: ${{baseM}} Months</div>
            </div>
          </div>
        </div>

        <!-- Catalyst & News Intelligence Radar -->
        <div class="mt-5 grid grid-cols-1 md:grid-cols-2 gap-3">
          <!-- Earnings Announcement Radar -->
          <div class="glass-card rounded-xl p-4 border border-slate-800">
            <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
              <i class="fa-solid fa-calendar-check text-emerald-400"></i> Board Meeting / Earnings Radar
            </h4>
            <div class="p-3 rounded-lg bg-slate-900/80 border border-slate-800">
              <div class="flex items-center gap-2">
                <span class="text-xs font-semibold text-slate-200">${{earn.badge || '✅ Safe'}}</span>
              </div>
              <div class="text-xs text-slate-400 mt-1">${{earn.text || 'No imminent earnings risk detected.'}}</div>
            </div>
          </div>

          <!-- 3-Day News Catalyst -->
          <div class="glass-card rounded-xl p-4 border border-slate-800">
            <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
              <i class="fa-solid fa-newspaper text-cyan-400"></i> 3-Day Catalyst News & Sentiment
            </h4>
            <div class="p-3 rounded-lg bg-slate-900/80 border border-slate-800">
              <div class="flex items-center justify-between text-xs mb-1">
                <span class="font-bold text-slate-300">${{news.sentiment || '⚪ Market Update'}}</span>
                <span class="text-[10px] text-slate-500">${{news.time_str || ''}}</span>
              </div>
              <div class="text-xs text-slate-300 line-clamp-2">${{news.title || 'No disruptive high-impact news in last 72 hours.'}}</div>
            </div>
          </div>
        </div>
      `;

      document.getElementById('inspectorModal').classList.remove('hidden');
    }}

    function closeInspector() {{
      document.getElementById('inspectorModal').classList.add('hidden');
    }}

    function updateModalWatchlistBtn(symbol) {{
      const btn = document.getElementById('modal-watchlist-btn');
      if (!btn) return;
      const isWatched = watchlist.includes(symbol);
      if (isWatched) {{
        btn.className = 'px-3.5 py-2 rounded-xl text-xs font-bold border transition flex items-center gap-2 bg-amber-500 text-slate-950 border-amber-400';
        btn.innerHTML = '<i class="fa-solid fa-star"></i> In Watchlist';
      }} else {{
        btn.className = 'px-3.5 py-2 rounded-xl text-xs font-bold border transition flex items-center gap-2 bg-slate-800 text-amber-400 border-slate-700 hover:bg-slate-700';
        btn.innerHTML = '<i class="fa-regular fa-star"></i> Add to Watchlist';
      }}
    }}

    // EXPORT TO CSV
    function exportCSV() {{
      const headers = ["Symbol", "Company", "Cap", "LTP", "10_EMA", "Diff_%", "Setup", "52W_High", "Dist_52W_%", "Base_Months", "PAT_Cr", "PAT_YoY", "Rev_Cr", "Rev_YoY", "OPM_%", "Badge"];
      const rows = STOCKS_DATA.map(s => {{
        const fin = s.intel?.financials || {{}};
        return [
          `"${{s.Symbol || ''}}"`,
          `"${{(s.Company_Name || '').replace(/"/g, '""')}}"`,
          `"${{s.Cap || ''}}"`,
          s.LTP,
          s.Monthly_10EMA,
          s['Diff_%'],
          `"${{s.Setup_Type || ''}}"`,
          s.High_52W,
          s['Dist_52W_%'],
          s.Base_Months,
          `"${{fin.pat_cr || ''}}"`,
          `"${{fin.pat_growth_fmt || ''}}"`,
          `"${{fin.revenue_cr || ''}}"`,
          `"${{fin.rev_growth_fmt || ''}}"`,
          `"${{fin.profit_margin_fmt || ''}}"`,
          `"${{fin.badge || ''}}"`
        ].join(',');
      }});

      const csvContent = "data:text/csv;charset=utf-8," + [headers.join(','), ...rows].join('\\n');
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", `NSE_Monthly_10EMA_Terminal_${{new Date().toISOString().slice(0,10)}}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }}
  </script>
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"[WebTerminal] Successfully generated Web Terminal at: {output_path}")

if __name__ == '__main__':
    build()
