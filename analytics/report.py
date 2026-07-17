"""
analytics/report.py — สร้างรายงาน Backtest (HTML Report)
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from datetime import datetime


def create_equity_chart(equity_df, symbol):
    """สร้างกราฟ Equity Curve (Plotly)"""
    if equity_df.empty:
        return ""

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=[
            f"📈 Equity Curve — {symbol}",
            "💰 Unrealized PnL",
            "📉 Drawdown"
        ]
    )

    fig.add_trace(
        go.Scatter(
            x=equity_df["timestamp"],
            y=equity_df["equity"],
            name="Equity",
            line=dict(color="#00ff88", width=2),
            fill="tozeroy",
            fillcolor="rgba(0,255,136,0.1)",
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Scatter(
            x=equity_df["timestamp"],
            y=equity_df["capital"],
            name="Realized Capital",
            line=dict(color="#888888", width=1, dash="dot"),
            visible="legendonly",
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Bar(
            x=equity_df["timestamp"],
            y=equity_df["unrealized_pnl"],
            name="Unrealized PnL",
            marker_color=[
                "#00ff88" if x >= 0 else "#ff4444"
                for x in equity_df["unrealized_pnl"]
            ],
        ),
        row=2, col=1
    )

    equity = equity_df["equity"].values
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak * 100
    fig.add_trace(
        go.Scatter(
            x=equity_df["timestamp"],
            y=-dd,
            name="Drawdown %",
            line=dict(color="#ff4444", width=1),
            fill="tozeroy",
            fillcolor="rgba(255,68,68,0.1)",
        ),
        row=3, col=1
    )

    fig.update_layout(
        height=600,
        template="plotly_dark",
        showlegend=True,
        title_text=f"Backtest Report — {symbol}",
    )
    fig.update_xaxes(title_text="Time", row=3, col=1)
    fig.update_yaxes(title_text="USD", row=1, col=1)
    fig.update_yaxes(title_text="USD", row=2, col=1)
    fig.update_yaxes(title_text="%", row=3, col=1)

    return fig.to_html(include_plotlyjs="cdn", full_html=False)


def create_trade_chart(trades_df):
    """สร้างกราฟวิเคราะห์การเทรด"""
    if trades_df.empty:
        return ""

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            "📊 PnL Distribution",
            "📈 Cumulative PnL",
            "⏰ Holding Time Distribution",
            "🔄 DCA Count Distribution"
        ]
    )

    fig.add_trace(
        go.Histogram(x=trades_df["pnl_usd"], nbinsx=50, name="PnL", marker_color="#00ff88"),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(y=trades_df["pnl_usd"].cumsum(), name="Cum PnL", line=dict(color="#00ff88", width=2), fill="tozeroy", fillcolor="rgba(0,255,136,0.1)"),
        row=1, col=2
    )
    fig.add_trace(
        go.Histogram(x=trades_df["holding_minutes"], nbinsx=30, name="Hold Time", marker_color="#4488ff"),
        row=2, col=1
    )
    dca_counts = trades_df["dca_count"].value_counts().sort_index()
    fig.add_trace(
        go.Bar(x=dca_counts.index, y=dca_counts.values, name="DCA Count", marker_color="#ffaa00"),
        row=2, col=2
    )
    fig.update_layout(height=500, template="plotly_dark", showlegend=False)
    return fig.to_html(include_plotlyjs="cdn", full_html=False)


def generate_html_report(symbol, stats, equity_df, trades_df, output_dir="reports"):
    """สร้างรายงาน HTML ครบถ้วน"""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    equity_chart = create_equity_chart(equity_df, symbol)
    trade_chart = create_trade_chart(trades_df)

    pnl_class = "positive" if stats.get("total_pnl_usd", 0) >= 0 else "negative"
    dd_class = "negative" if stats.get("max_drawdown_pct", 0) > 0 else "positive"

    trade_rows = ""
    if not trades_df.empty:
        recent = trades_df.tail(20).iloc[::-1]
        for _, t in recent.iterrows():
            pc = "positive" if t["pnl_usd"] >= 0 else "negative"
            trade_rows += f"""
            <tr>
                <td>{str(t['open_time'])[:19]}</td>
                <td>{str(t['close_time'])[:19]}</td>
                <td>{t['side']}</td>
                <td>${t['ep']:,.2f}</td>
                <td>${t['bep']:,.2f}</td>
                <td>{t['dca_count']}</td>
                <td class="{pc}">${t['pnl_usd']:,.2f}</td>
                <td>{t['close_reason']}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report — {symbol}</title>
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
        .chart-container {{ margin: 20px 0; background: #161b22; border-radius: 8px; padding: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #30363d; }}
        th {{ color: #58a6ff; background: #161b22; }}
        tr:hover {{ background: #1c2128; }}
        .footer {{ text-align: center; color: #484f58; margin-top: 40px; padding: 20px; border-top: 1px solid #30363d; }}
    </style>
</head>
<body>
<div class="container">
    <h1>📈 Backtest Report — {symbol}</h1>
    <p style="text-align:center;color:#8b949e;">Mean Reversion + DCA (RSI Signal) | {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>

    <h2>📊 Summary</h2>
    <div class="stats-grid">
        <div class="stat-card"><div class="label">Total Trades</div><div class="value">{stats['total_trades']:,}</div><div class="unit">trades</div></div>
        <div class="stat-card"><div class="label">Win Rate</div><div class="value {'positive' if stats['win_rate']>=90 else 'negative'}">{stats['win_rate']:.2f}%</div><div class="unit">{stats['win_count']:,}W / {stats['loss_count']:,}L</div></div>
        <div class="stat-card"><div class="label">Total PnL</div><div class="value {pnl_class}">${stats['total_pnl_usd']:,.2f}</div><div class="unit">{stats['total_pnl_pct']:+.2f}%</div></div>
        <div class="stat-card"><div class="label">Final Equity</div><div class="value">${stats['final_equity']:,.2f}</div><div class="unit">USD</div></div>
        <div class="stat-card"><div class="label">Max Drawdown</div><div class="value {dd_class}">{stats['max_drawdown_pct']:.2f}%</div><div class="unit">${stats['max_drawdown_usd']:,.2f}</div></div>
        <div class="stat-card"><div class="label">Total Fees</div><div class="value">${stats['total_fees_usd']:,.2f}</div><div class="unit">USD</div></div>
        <div class="stat-card"><div class="label">Avg Hold Time</div><div class="value">{stats['avg_holding_minutes']:.0f}</div><div class="unit">min</div></div>
        <div class="stat-card"><div class="label">Avg DCA Count</div><div class="value">{stats['avg_dca_count']:.1f}</div><div class="unit">max {stats['max_dca_count']}</div></div>
    </div>

    <h2>📈 Equity Curve</h2>
    <div class="chart-container">{equity_chart}</div>

    <h2>📊 Trade Analysis</h2>
    <div class="chart-container">{trade_chart}</div>

    <h2>📋 Trade Log (Last 20)</h2>
    <table><tr><th>Open</th><th>Close</th><th>Side</th><th>EP</th><th>BEP</th><th>DCA</th><th>PnL</th><th>Reason</th></tr>{trade_rows}</table>

    <div class="footer"><p>Crypto Backtest System — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p></div>
</div>
</body></html>"""

    report_path = output_path / f"{symbol}_report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"💾 Report: {report_path}")
    return str(report_path)