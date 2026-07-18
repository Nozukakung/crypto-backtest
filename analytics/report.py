"""
analytics/report.py — HTML Report (Optimized: Sampling + Lightweight Charts)
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime


MAX_POINTS = 2000  # จำกัดจุดเพื่อให้ไฟล์เล็กและเครื่องไม่ค้าง (1-2 MB)


def sample_dataframe(df, max_points=MAX_POINTS):
    """Downsample dataframe to max_points using uniform sampling"""
    if len(df) <= max_points:
        return df
    step = len(df) // max_points + 1
    return df.iloc[::step].reset_index(drop=True)


def create_equity_chart_data(equity_df, symbol):
    """สร้างข้อมูล chart แบบ JSON สำหรับ Chart.js"""
    df = sample_dataframe(equity_df)
    df = df.copy()

    # คำนวณ drawdown
    equity = df["equity"].values
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak * 100

    return {
        "labels": [str(t)[:16] for t in df["timestamp"]],
        "equity": [round(float(x), 2) for x in df["equity"]],
        "drawdown": [round(float(x), 2) for x in -dd],
    }


def create_trade_chart_data(trades_df):
    """ข้อมูลสำหรับ trade analysis charts"""
    if trades_df.empty:
        return {"pnl": [], "cum_pnl": [], "hold_time": [], "dca": {}}

    # Sample trades if too many
    sampled = trades_df
    if len(trades_df) > MAX_POINTS:
        sampled = trades_df.sample(n=MAX_POINTS, random_state=42)

    # คำนวณ bins สำหรับ PnL Distribution (แบบ histogram ง่ายๆ ด้วย Chart.js bar)
    # แทนที่จะใช้ histogram complex plugin เราจะจำลองเป็น frequency map
    pnl_values = sampled["pnl_usd"].values
    counts, bins = np.histogram(pnl_values, bins=20)
    pnl_dist = {
        "labels": [f"{round(bins[i], 1)} to {round(bins[i+1], 1)}" for i in range(len(bins)-1)],
        "values": [int(x) for x in counts]
    }

    # Cumulative PnL (sampled)
    cum_pnl = sampled["pnl_usd"].cumsum().values

    # Holding time
    ht_counts, ht_bins = np.histogram(sampled["holding_minutes"].values, bins=20)
    hold_dist = {
        "labels": [f"{int(ht_bins[i])}-{int(ht_bins[i+1])}m" for i in range(len(ht_bins)-1)],
        "values": [int(x) for x in ht_counts]
    }

    # DCA Count
    dca_counts = trades_df["dca_count"].value_counts().sort_index()

    return {
        "pnl_dist": pnl_dist,
        "cum_pnl": [round(float(x), 2) for x in cum_pnl],
        "hold_dist": hold_dist,
        "dca": {str(k): int(v) for k, v in dca_counts.items()},
    }


def generate_html_report(symbol, stats, equity_df, trades_df, output_dir="reports"):
    """สร้างรายงาน HTML แบบ Lightweight (ใช้ Chart.js)"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    equity_data = create_equity_chart_data(equity_df, symbol)
    trade_data = create_trade_chart_data(trades_df)

    pnl_class = "positive" if stats.get("total_pnl_usd", 0) >= 0 else "negative"
    dd_class = "negative" if stats.get("max_drawdown_pct", 0) > 0 else "positive"

    trade_rows = ""
    if not trades_df.empty:
        recent = trades_df.tail(20).iloc[::-1]
        for _, t in recent.iterrows():
            pc = "positive" if t["pnl_usd"] >= 0 else "negative"
            trade_rows += f"""
            <tr>
                <td>{str(t['open_time'])[:16]}</td>
                <td>{str(t['close_time'])[:16]}</td>
                <td>{t['side']}</td>
                <td>${t['ep']:,.2f}</td>
                <td>${t['bep']:,.2f}</td>
                <td>{t['dca_count']}</td>
                <td class="{pc}">${t['pnl_usd']:,.2f}</td>
                <td>{t['close_reason']}</td>
            </tr>"""

    # ป้องกัน f-string template issue ด้วยการแยกใส่ JSON ตรงๆ
    equity_json = json.dumps(equity_data)
    trade_json = json.dumps(trade_data)

    template = """<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report — {SYMBOL}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #58a6ff; text-align: center; margin: 30px 0; font-size: 2em; }
        h2 { color: #79c0ff; margin: 20px 0 10px; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
        .stat-card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; text-align: center; }
        .stat-card .label { color: #8b949e; font-size: 0.9em; }
        .stat-card .value { color: #f0f6fc; font-size: 1.8em; font-weight: bold; margin: 5px 0; }
        .stat-card .unit { color: #8b949e; font-size: 0.8em; }
        .positive { color: #3fb950; } .negative { color: #f85149; }
        .chart-container { background: #161b22; border-radius: 8px; padding: 20px; margin: 20px 0; height: 350px; }
        .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        @media (max-width: 900px) { .chart-grid { grid-template-columns: 1fr; } }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; }
        th { color: #58a6ff; background: #161b22; }
        tr:hover { background: #1c2128; }
        .footer { text-align: center; color: #484f58; margin-top: 40px; padding: 20px; border-top: 1px solid #30363d; }
    </style>
</head>
<body>
<div class="container">
    <h1>📈 Backtest Report — {SYMBOL}</h1>
    <p style="text-align:center;color:#8b949e;">Mean Reversion + DCA (RSI Signal) | {DATE}</p>

    <h2>📊 Summary</h2>
    <div class="stats-grid">
        <div class="stat-card"><div class="label">Total Trades</div><div class="value">{TOTAL_TRADES}</div><div class="unit">trades</div></div>
        <div class="stat-card"><div class="label">Win Rate</div><div class="value {WIN_CLASS}">{WIN_RATE}%</div><div class="unit">{WIN_COUNT}W / {LOSS_COUNT}L</div></div>
        <div class="stat-card"><div class="label">Total PnL</div><div class="value {PNL_CLASS}">${TOTAL_PNL}</div><div class="unit">{TOTAL_PNL_PCT}%</div></div>
        <div class="stat-card"><div class="label">Final Equity</div><div class="value">${FINAL_EQUITY}</div><div class="unit">USD</div></div>
        <div class="stat-card"><div class="label">Max Drawdown</div><div class="value {DD_CLASS}">{MAX_DD}%</div><div class="unit">${MAX_DD_USD}</div></div>
        <div class="stat-card"><div class="label">Total Fees</div><div class="value">${TOTAL_FEES}</div><div class="unit">USD</div></div>
        <div class="stat-card"><div class="label">Avg Hold Time</div><div class="value">{AVG_HOLD}</div><div class="unit">min</div></div>
        <div class="stat-card"><div class="label">Avg DCA Count</div><div class="value">{AVG_DCA}</div><div class="unit">max {MAX_DCA}</div></div>
    </div>

    <h2>📈 Equity Curve</h2>
    <div class="chart-grid">
        <div class="chart-container"><canvas id="equityChart"></canvas></div>
        <div class="chart-container"><canvas id="drawdownChart"></canvas></div>
    </div>

    <h2>📊 Trade Analysis</h2>
    <div class="chart-grid">
        <div class="chart-container"><canvas id="pnlDistChart"></canvas></div>
        <div class="chart-container"><canvas id="cumPnlChart"></canvas></div>
        <div class="chart-container"><canvas id="holdTimeChart"></canvas></div>
        <div class="chart-container"><canvas id="dcaChart"></canvas></div>
    </div>

    <h2>📋 Trade Log (Last 20)</h2>
    <table><tr><th>Open</th><th>Close</th><th>Side</th><th>EP</th><th>BEP</th><th>DCA</th><th>PnL</th><th>Reason</th></tr>{TRADE_ROWS}</table>

    <div class="footer"><p>Crypto Backtest System — {DATE}</p></div>
</div>

<script>
const equityData = %EQUITY_JSON%;
const tradeData = %TRADE_JSON%;

const GREEN = '#3fb950', RED = '#f85149', BLUE = '#58a6ff', YELLOW = '#d29922', GRAY = '#8b949e';

// 1. Equity Chart
new Chart(document.getElementById('equityChart'), {
    type: 'line',
    data: {
        labels: equityData.labels,
        datasets: [
            { label: 'Equity', data: equityData.equity, borderColor: GREEN, backgroundColor: 'rgba(63,185,80,0.1)', fill: true, tension: 0.1, pointRadius: 0 }
        ]
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#c9d1d9' } }, title: { display: true, text: 'Equity Curve', color: '#c9d1d9' } }, scales: { x: { grid: { color: '#30363d' }, ticks: { color: '#8b949e', maxTicksLimit: 10 } }, y: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } } } }
});

// 2. Drawdown Chart
new Chart(document.getElementById('drawdownChart'), {
    type: 'line',
    data: { labels: equityData.labels, datasets: [{ label: 'Drawdown %', data: equityData.drawdown, borderColor: RED, backgroundColor: 'rgba(248,81,73,0.1)', fill: true, tension: 0.1, pointRadius: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: '#c9d1d9' } }, title: { display: true, text: 'Drawdown %', color: '#c9d1d9' } }, scales: { x: { grid: { color: '#30363d' }, ticks: { color: '#8b949e', maxTicksLimit: 10 } }, y: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } } } }
});

// 3. PnL Distribution (Bar chart)
new Chart(document.getElementById('pnlDistChart'), {
    type: 'bar',
    data: { labels: tradeData.pnl_dist.labels, datasets: [{ label: 'Frequency', data: tradeData.pnl_dist.values, backgroundColor: 'rgba(63,185,80,0.6)', borderColor: GREEN, borderWidth: 1 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: 'PnL Distribution', color: '#c9d1d9' } }, scales: { x: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } }, y: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } } } }
});

// 4. Cumulative PnL
new Chart(document.getElementById('cumPnlChart'), {
    type: 'line',
    data: { labels: tradeData.cum_pnl.map((_,i)=>i), datasets: [{ label: 'Cumulative PnL', data: tradeData.cum_pnl, borderColor: GREEN, backgroundColor: 'rgba(63,185,80,0.1)', fill: true, tension: 0.1, pointRadius: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: 'Cumulative PnL', color: '#c9d1d9' } }, scales: { x: { display: false }, y: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } } } }
});

// 5. Holding Time Distribution
new Chart(document.getElementById('holdTimeChart'), {
    type: 'bar',
    data: { labels: tradeData.hold_dist.labels, datasets: [{ label: 'Frequency', data: tradeData.hold_dist.values, backgroundColor: 'rgba(88,166,255,0.6)', borderColor: BLUE, borderWidth: 1 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: 'Holding Time Distribution', color: '#c9d1d9' } }, scales: { x: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } }, y: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } } } }
});

// 6. DCA Count
const dcaLabels = Object.keys(tradeData.dca).sort((a,b)=>a-b);
const dcaValues = dcaLabels.map(k => tradeData.dca[k]);
new Chart(document.getElementById('dcaChart'), {
    type: 'bar',
    data: { labels: dcaLabels, datasets: [{ label: 'Frequency', data: dcaValues, backgroundColor: 'rgba(210,153,34,0.6)', borderColor: YELLOW, borderWidth: 1 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: 'DCA Count Distribution', color: '#c9d1d9' } }, scales: { x: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } }, y: { grid: { color: '#30363d' }, ticks: { color: '#8b949e' } } } }
});
</script>
</body></html>"""

    # ทำแทนที่ string ธรรมดา (หลีกเลี่ยง f-string formatting issue)
    html_filled = template \
        .replace("{SYMBOL}", symbol) \
        .replace("{DATE}", datetime.now().strftime("%Y-%m-%d %H:%M")) \
        .replace("{TOTAL_TRADES}", f"{stats['total_trades']:,}") \
        .replace("{WIN_CLASS}", "positive" if stats['win_rate']>=90 else "negative") \
        .replace("{WIN_RATE}", f"{stats['win_rate']:.2f}") \
        .replace("{WIN_COUNT}", f"{stats['win_count']:,}") \
        .replace("{LOSS_COUNT}", f"{stats['loss_count']:,}") \
        .replace("{PNL_CLASS}", pnl_class) \
        .replace("{TOTAL_PNL}", f"{stats['total_pnl_usd']:,.2f}") \
        .replace("{TOTAL_PNL_PCT}", f"{stats['total_pnl_pct']:+.2f}") \
        .replace("{FINAL_EQUITY}", f"{stats['final_equity']:,.2f}") \
        .replace("{DD_CLASS}", dd_class) \
        .replace("{MAX_DD}", f"{stats['max_drawdown_pct']:.2f}") \
        .replace("{MAX_DD_USD}", f"{stats['max_drawdown_usd']:,.2f}") \
        .replace("{TOTAL_FEES}", f"{stats['total_fees_usd']:,.2f}") \
        .replace("{AVG_HOLD}", f"{stats['avg_holding_minutes']:.0f}") \
        .replace("{AVG_DCA}", f"{stats['avg_dca_count']:.1f}") \
        .replace("{MAX_DCA}", f"{stats['max_dca_count']}") \
        .replace("{TRADE_ROWS}", trade_rows) \
        .replace("%EQUITY_JSON%", equity_json) \
        .replace("%TRADE_JSON%", trade_json)

    report_path = output_path / f"{symbol}_report.html"
    report_path.write_text(html_filled, encoding="utf-8")
    size_mb = report_path.stat().st_size / 1024 / 1024
    print(f"Report saved: {report_path} size={size_mb:.2f}MB")
    return str(report_path)