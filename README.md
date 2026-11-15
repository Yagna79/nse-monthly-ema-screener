# 📈 NSE Monthly 10-EMA & Financial Intelligence Terminal (Web Edition)

Institutional-grade, cloud-automated stock screener for the National Stock Exchange of India (NSE). Screens 1,450+ stocks for Monthly 10-EMA pullbacks combined with 12-month 20%+ momentum bursts, quarterly fundamentals, earnings radar, and sector rotation heatmaps.

---

## 🌟 Key Features

1. **Monthly 10-EMA Pullback Engine**:
   - Detects stocks in the 0% to 4% "Sweet Zone" near Monthly 10-EMA.
   - Validates institutional accumulation with 12-Month 20%+ momentum filter.
   - 52-Week High & ATH proximity tracking.

2. **Quarterly Financial Intelligence (Screener.in & Yahoo)**:
   - Quarterly Sales / Revenue (₹ Cr) & YoY % Growth.
   - Net Profit (PAT in ₹ Cr) & YoY % Growth.
   - Operating Profit Margin (OPM %) & Return on Equity (ROE %).
   - Super Growth & Multibagger profile badges.

3. **Sector Rotation Heatmap**:
   - Live visual aggregation of sectors (Capital Goods, Healthcare, IT, Energy, etc.).
   - Instant 1-click filtering by sector tailwinds.

4. **Event & Catalyst Radar**:
   - Board meeting earnings announcement tracker (Safe vs Alert within 10 days).
   - 3-day high-impact catalyst news with sentiment analysis.

5. **Automated Cloud Updates (GitHub Actions)**:
   - Runs automatically every Monday–Friday at 4:00 PM IST (Market Close).
   - Re-scans universe, recalculates EMAs, updates financial cache, and deploys to GitHub Pages.
   - Zero hosting fees, 100% free forever.

6. **Telegram Instant Buy Zone Alerts**:
   - Sends formatted alert notifications to your Telegram when top super-growth stocks enter the 10-EMA buy zone.

---

## 🚀 How to Put This Live on GitHub (Step-by-Step)

### Step 1: Create a New GitHub Repository
1. Open [github.com](https://github.com) and log in.
2. Click **New Repository** (green button).
3. Name it: `nse-monthly-ema-screener` (or any name you like).
4. Set visibility to **Public** (required for free GitHub Pages).
5. Leave "Add a README file" unchecked, then click **Create repository**.

### Step 2: Upload Files
Upload all files from this folder (`F:\NSE_Monthly_EMA_Screener_Web`) to the repository:
- You can simply click **"uploading an existing file"** in the browser and drag-and-drop the files, or use Git:
```bash
git init
git add .
git commit -m "Initial commit: NSE 10-EMA Web Terminal"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/nse-monthly-ema-screener.git
git push -u origin main
```

### Step 3: Enable GitHub Pages
1. Go to repository **Settings** -> **Pages** (on the left menu).
2. Under **Build and deployment** -> **Source**, select:
   **GitHub Actions** (NOT "Deploy from a branch").
3. That's it! GitHub will now host your website at:  
   `https://<YOUR_USERNAME>.github.io/nse-monthly-ema-screener/`

### Step 4 (Optional): Enable Telegram Notifications
If you want instant alerts on your phone:
1. Create a bot using [@BotFather](https://t.me/BotFather) on Telegram and copy the **Bot Token**.
2. Get your Chat ID using [@userinfobot](https://t.me/userinfobot).
3. In your GitHub repository:
   - Go to **Settings** -> **Secrets and variables** -> **Actions**.
   - Click **New repository secret**.
   - Add:
     - `TELEGRAM_BOT_TOKEN`: Your bot token
     - `TELEGRAM_CHAT_ID`: Your chat ID
4. Now, every day at 4:00 PM IST, you will receive top buy zone setups directly on your phone!

---

## 💻 Manual / Local Testing
To test or update the web terminal locally on your computer:
```bash
python build_web_terminal.py
```
Double click `index.html` to open in any web browser.
