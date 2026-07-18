"""
analytics/report.py — HTML Report v3 (Exchange Precision Display)
แสดงผลทศนิยมตามจริงของแต่ละเหรียญ
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from engine.exchange import get_symbol_info, round_to_precision


MAX_POINTS = 2000


def fmt_price(symbol, value):
    """แสดงราคาตาม Price Precision ของแต่ละเหรียญ"""
    info = get_symbol_info(symbol)
    if info.price_precision < 0:
        # เช่น precision=-1 = ปัดเป็นหลัก 10
        return f"${round_to_precision(value, info.price_precision):,.0f}"
    return f"${value:,.{info.price_precision}f}"


def fmt_qty(symbol, value):
    """แสดงจำนวนตาม Qty Precision ของแต่ละเหรียญ"""
    info = get_symbol_info(symbol)
    if info.qty_precision == 0:
        return f"{value:,.0f}"
    return f"{value:,.{info.qty_precision}f}"


def fmt_usd(value):
    """แสดงเงิน USD (ใช้ 2 ตำแหน่งเท่ากันตลอด)"""
    return f"${value:,.2f}"


def fmt_pct(x):
    return f"{x:+.2f}%"


def color_class(x):
    return "positive" if x >= 0 else "negative"


def sample_dataframe(df, max_points=MAX_POINTS):
    if len(df) <= max_points:
        return df
    step = len(df) // max_points + 1
    return df.iloc[::step].reset_index(drop=True)


def create_equity_chart_data(equity_df):
    df = sample_dataframe(equity_df)
    df = df.copy()
    equity = df["equity"].values
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak * 100
    return {
        "labels": [str(t)[:16] for t in df["timestamp"]],
        "equity": [round(float(x), 2) for x in equity],
        "drawdown": [round(float(x), 2) for x in -dd],
    }


def create_trade_chart_data(trades_df):
    if trades_df.empty:
        return {"pnl": [], "cum_pnl": [], "hold_time": [], "dca": {"labels": [], "values": []}}

    sampled = trades_df
    if len(trades_df) > MAX_POINTS:
        sampled = trades_df.sample(n=MAX_POINTS, random_state=42)

    pnl = sampled["pnl_usd"].values
    hold_time = sampled["holding_minutes"].values
    dca_counts = sampled["dca_count"].values

    dca_hist = {}
    for d in dca_counts:
        dca_hist[int(d)] = dca_hist.get(int(d), 0) + 1
    dca_labels = sorted(dca_hist.keys())
    dca_values = [dca_hist[k] for k in dca_labels]

    cum_pnl = np.cumsum(pnl)

    return {
        "pnl": [round(float(x), 2) for x in pnl],
        "cum_pnl": [round(float(x), 2) for x in cum_pnl],
        "hold_time": [int(x) for x in hold_time],
        "dca": {"labels": [str(x) for x in dca_labels], "values": dca_values},
    }


def generate_html_report(symbol, stats, equity_df, trades_df, result=None, output_dir="reports"):
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    info = get_symbol_info(symbol)

    # Separate closed vs END_OF_DATA
    normal_trades = trades_df[trades_df["close_reason"] != "END_OF_DATA"]
    end_data_trades = trades_df[trades_df["close_reason"] == "END_OF_DATA"]

    normal_count = len(normal_trades)
    normal_win = int((normal_trades["pnl_usd"] > 0).sum())
    normal_pnl = float(normal_trades["pnl_usd"].sum()) if normal_count > 0 else 0
    normal_win_rate = normal_win / normal_count * 100 if normal_count > 0 else 0

    end_count = len(end_data_trades)
    end_pnl = float(end_data_trades["pnl_usd"].sum()) if end_count > 0 else 0

    equity_data = create_equity_chart_data(equity_df)
    trade_data = create_trade_chart_data(trades_df)

    # Calculate win/loss counts
    win_count = len([x for x in trade_data["pnl"] if x > 0])
    loss_count = len([x for x in trade_data["pnl"] if x < 0])

    # Prepare trade table (last 20)
    display_trades = trades_df.tail(20).iloc[::-1]

    trade_rows = []
    for _, row in display_trades.iterrows():
        open_time = str(row["open_time"])[:16]
        close_time = str(row["close_time"])[:16]
        side = row["side"]
        ep = fmt_price(symbol, row['ep'])
        bep = fmt_price(symbol, row['bep'])
        qty = fmt_qty(symbol, row.get('qty', row['ep'] * row['dca_count'] / row['ep'] if row['ep'] > 0 else 0))
        dca = int(row["dca_count"])
        pnl = row["pnl_usd"]
        reason = row["close_reason"]
        pnl_class = "positive" if pnl >= 0 else "negative"
        pnl_str = fmt_usd(pnl)
        trade_rows.append(f"""
            <tr>
                <td>{open_time}</td>
                <td>{close_time}</td>
                <td>{side}</td>
                <td>{ep}</td>
                <td>{bep}</td>
                <td>{dca}</td>
                <td class="{pnl_class}">{pnl_str}</td>
                <td>{reason}</td>
            </tr>""")

    trade_table = "".join(trade_rows)

    # Exchange info display
    exchange_info = f"""
    <div class="info-box">
        <h3>⚙️ Exchange Rules ({symbol})</h3>
        <p>Price Precision: {info.price_precision} ตำแหน่ง (เช่น {fmt_price(symbol, 12345.6)})</p>
        <p>Qty Precision: {info.qty_precision} ตำแหน่ง (เช่น {fmt_qty(symbol, 1.234)})</p>
        <p>Min Qty: {fmt_qty(symbol, info.min_qty)} | Min Notional: ${info.min_notional}</p>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report — {symbol}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #58a6ff; text-align: center; margin: 30px 0; font-size: 2em; }}
        h2 {{ color: #79c0ff; margin: 20px 0 10px; border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; text-align: center; }}
        .stat-card .label {{ color: #8b949e; font-size: 0.9em; }}
        .stat-card .value {{ color: #f0f6fc; font-size: 1.8em; font-weight: bold; margin: 5px 0; }}
        .stat-card .unit {{ color: #8b949e; font-size: 0.8em; }}
        .positive {{ color: #3fb950; }} .negative {{ color: #f85149; }}
        .warning {{ color: #d29922; }}
        .chart-container {{ background: #161b22; border-radius: 8px; padding: 20px; margin: 20px 0; height: 350px; }}
        .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        @media (max-width: 900px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; }}
        th {{ color: #58a6ff; background: #161b22; }}
        tr:hover {{ background: #1c2128; }}
        .footer {{ text-align: center; color: #484f58; margin-top: 40px; padding: 20px; border-top: 1px solid #30363d; }}
        .info-box {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; margin: 15px 0; }}
        .info-box.warning {{ border-color: #d29922; background: #2d2400; }}
        .info-box h3 {{ color: #d29922; margin-bottom: 10px; }}
        .info-box p {{ color: #c9d1d9; margin: 5px 0; }}
    </style>
</head>
<body>
<div class="container">
    <h1>📈 Backtest Report — {symbol}</h1>
    <p style="text-align:center;color:#8b949e;">Mean Reversion + DCA (RSI Signal) | {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

    {exchange_info}

    <div class="info-box warning">
        <h3>⚠️ หมายเหตุสำคัญ</h3>
        <p><strong>Equity Curve = Realized Equity เท่านั้น</strong> (ติดตามเฉพาะ PnL ที่ปิด position แล้ว)</p>
        <p>Max Drawdown = {stats.get('max_drawdown_pct', 0):.2f}% (ตาม realized capital PnL)</p>
        <p><strong>END_OF_DATA = Position ค้างตอนจบข้อมูล</strong> ยังไม่ได้ปิด TP (ในจริงจะรอต่อจนปิดได้)</p>
        <p><strong>ทุกราคา/จำนวนในตาราง = ปัดตาม Exchange Rules จริงแล้ว</strong></p>
    </div>

    <h2>📊 Summary (Closed Positions Only)</h2>
    <div class="stats-grid">
        <div class="stat-card"><div class="label">Closed Trades</div><div class="value">{normal_count:,}</div><div class="unit">trades</div></div>
        <div class="stat-card"><div class="label">Win Rate</div><div class="value positive">{normal_win_rate:.2f}%</div><div class="unit">{normal_win}W / {normal_count - normal_win}L</div></div>
        <div class="stat-card"><div class="label">Closed PnL</div><div class="value {color_class(normal_pnl)}">{fmt_usd(normal_pnl)}</div><div class="unit">{fmt_pct(normal_pnl / stats.get('initial_capital', 10000) * 100)}</div></div>
        <div class="stat-card"><div class="label">Final Equity</div><div class="value">{fmt_usd(stats.get('final_equity', 0))}</div><div class="unit">USD</div></div>
        <div class="stat-card"><div class="label">Max Drawdown</div><div class="value positive">{stats.get('max_drawdown_pct', 0):.2f}%</div><div class="unit">{fmt_usd(stats.get('max_drawdown_usd', 0))}</div></div>
        <div class="stat-card"><div class="label">Total Fees</div><div class="value">{fmt_usd(stats.get('total_fees_usd', 0))}</div><div class="unit">USD</div></div>
        <div class="stat-card"><div class="label">Avg Hold Time</div><div class="value">{stats.get('avg_holding_minutes', 0):.0f}</div><div class="unit">min</div></div>
        <div class="stat-card"><div class="label">Avg DCA Count</div><div class="value">{stats.get('avg_dca_count', 0):.1f}</div><div class="unit">max {stats.get('max_dca_count', 0)}</div></div>
    </div>

    {f'''
    <h2>⚠️ END_OF_DATA Positions (ยังไม่ได้ปิด TP)</h2>
    <div class="stats-grid">
        <div class="stat-card"><div class="label">Open Positions</div><div class="value warning">{end_count}</div><div class="unit">positions</div></div>
        <div class="stat-card"><div class="label">Unrealized PnL</div><div class="value negative">{fmt_usd(end_pnl)}</div><div class="unit">{fmt_pct(end_pnl / stats.get('initial_capital', 10000) * 100)}</div></div>
    </div>
    ''' if end_count > 0 else ''}

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

    <h2>📋 Trade Log (Last 20) — ทศนิยมตาม Exchange Rules จริง</h2>
    <p style="color:#8b949e;margin-bottom:10px;">
        Price: {info.price_precision} ตำแหน่ง | Qty: {info.qty_precision} ตำแหน่ง
    </p>
    <table>
        <tr><th>Open</th><th>Close</th><th>Side</th><th>EP (Price)</th><th>BEP (Price)</th><th>DCA</th><th>PnL (USD)</th><th>Reason</th></tr>
        {trade_table}
    </table>

    <div class="footer">
        <p>Generated by Crypto Backtest Engine v2.1</p>
        <p>Strategy: Mean Reversion + DCA (RSI Signal, TF 1m) | Exchange Precision: {symbol}</p>
    </div>

<script>
const equityData = {json.dumps(equity_data)};
const tradeData = {json.dumps(trade_data)};
const GREEN = '#3fb950';
const RED = '#f85149';
const BLUE = '#58a6ff';
const GRAY = '#8b949e';
const GRID = '#30363d';

const commonOpts = {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
        legend: {{ labels: {{ color: '#c9d1d9', font: {{ size: 11 }} }} }},
        title: {{ display: true, color: '#c9d1d9', font: {{ size: 13 }} }}
    }},
    scales: {{
        x: {{ grid: {{ color: GRID }}, ticks: {{ color: GRAY, maxTicksLimit: 10 }} }},
        y: {{ grid: {{ color: GRID }}, ticks: {{ color: GRAY }} }}
    }}
}};

new Chart(document.getElementById('equityChart').getContext('2d'), {{
    type: 'line',
    data: {{
        labels: equityData.labels,
        datasets: [{{
            label: 'Equity',
            data: equityData.equity,
            borderColor: GREEN,
            backgroundColor: 'rgba(63,185,80,0.1)',
            fill: true,
            tension: 0.1,
            pointRadius: 0
        }}]
    }},
    options: {{ ...commonOpts, plugins: {{ ...commonOpts.plugins, title: {{ ...commonOpts.plugins.title, text: 'Equity Curve (Realized)' }} }} }}
}});

new Chart(document.getElementById('drawdownChart').getContext('2d'), {{
    type: 'line',
    data: {{
        labels: equityData.labels,
        datasets: [{{
            label: 'Drawdown %',
            data: equityData.drawdown,
            borderColor: RED,
            backgroundColor: 'rgba(248,81,73,0.1)',
            fill: true,
            tension: 0.1,
            pointRadius: 0
        }}]
    }},
    options: {{ ...commonOpts, plugins: {{ ...commonOpts.plugins, title: {{ ...commonOpts.plugins.title, text: 'Drawdown % (Realized)' }} }} }}
}});

new Chart(document.getElementById('pnlDistChart').getContext('2d'), {{
    type: 'bar',
    data: {{
        labels: ['Wins', 'Losses'],
        datasets: [{{
            label: 'Count',
            data: [{win_count}, {loss_count}],
            backgroundColor: ['rgba(63,185,80,0.7)', 'rgba(248,81,73,0.7)'],
            borderColor: [GREEN, RED],
            borderWidth: 1
        }}]
    }},
    options: {{ ...commonOpts, plugins: {{ ...commonOpts.plugins, title: {{ ...commonOpts.plugins.title, text: 'Win/Loss Distribution' }} }} }}
}});

new Chart(document.getElementById('cumPnlChart').getContext('2d'), {{
    type: 'line',
    data: {{
        labels: Array.from({{length: tradeData.cum_pnl.length}}, (_, i) => i + 1),
        datasets: [{{
            label: 'Cumulative PnL',
            data: tradeData.cum_pnl,
            borderColor: BLUE,
            backgroundColor: 'rgba(88,166,255,0.1)',
            fill: true,
            tension: 0.1,
            pointRadius: 0
        }}]
    }},
    options: {{ ...commonOpts, plugins: {{ ...commonOpts.plugins, title: {{ ...commonOpts.plugins.title, text: 'Cumulative PnL' }} }} }}
}});

new Chart(document.getElementById('holdTimeChart').getContext('2d'), {{
    type: 'bar',
    data: {{
        labels: ['<10m', '10-30m', '30-60m', '1-2h', '2-4h', '4h+'],
        datasets: [{{
            label: 'Trades',
            data: (() => {{
                const bins = [0, 0, 0, 0, 0, 0];
                tradeData.hold_time.forEach(h => {{
                    if (h < 10) bins[0]++;
                    else if (h < 30) bins[1]++;
                    else if (h < 60) bins[2]++;
                    else if (h < 120) bins[3]++;
                    else if (h < 240) bins[4]++;
                    else bins[5]++;
                }});
                return bins;
            }})(),
            backgroundColor: 'rgba(88,166,255,0.7)',
            borderColor: BLUE,
            borderWidth: 1
        }}]
    }},
    options: {{ ...commonOpts, plugins: {{ ...commonOpts.plugins, title: {{ ...commonOpts.plugins.title, text: 'Holding Time Distribution' }} }} }}
}});

new Chart(document.getElementById('dcaChart').getContext('2d'), {{
    type: 'bar',
    data: {{
        labels: tradeData.dca.labels,
        datasets: [{{
            label: 'DCA Count',
            data: tradeData.dca.values,
            backgroundColor: 'rgba(210,153,34,0.7)',
            borderColor: '#d29922',
            borderWidth: 1
        }}]
    }},
    options: {{ ...commonOpts, plugins: {{ ...commonOpts.plugins, title: {{ ...commonOpts.plugins.title, text: 'DCA Count Distribution' }} }} }}
}});
</script>
</body>
</html>"""

    report_path = output_path / f"{symbol}_report.html"
    report_path.write_text(html, encoding="utf-8")
    size_mb = report_path.stat().st_size / 1024 / 1024
    print(f"Report saved: {report_path} ({size_mb:.2f} MB)")