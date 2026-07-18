"""
strategies/trend_following.py — Trend Following (Donchian Breakout v2.0)
ปรับ Logic ให้เข้มขึ้น:
- ใช้ EMA 200 เป็น Trend Filter (Long ได้ก็ต่อเมื่อ Price > EMA 200)
- Breakout ต้อง Close นอก Channel (ไม่ใช่แค่ High touch)
- Volume confirmation
- ใช้ Timeframe 4H แทน 1H
"""
import yaml
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional

CONFIG_DIR = Path(__file__).parent.parent / "config"
DATA_DIR = Path(__file__).parent.parent / "data" / "parquet"
REPORT_DIR = Path(__file__).parent.parent / "reports"


@dataclass
class Trade:
    symbol: str
    side: str
    entry_time: str
    entry_price: float
    exit_time: Optional[str]
    exit_price: Optional[float]
    size_usd: float
    pnl_usd: float = 0.0
    holding_hours: float = 0.0
    exit_reason: str = ""


@dataclass
class TrendConfig:
    donchian_period: int = 20
    atr_period: int = 14
    ema_period: int = 200           # Trend filter
    trailing_stop_multiplier: float = 2.0
    position_size_usd: float = 2000.0  # ใหญ่ขึ้น ลดจำนวน trade
    leverage: int = 5
    fee_rate: float = 0.0002
    timeframe: str = "4H"           # 4H แทน 1H


def load_4h_data(symbol: str) -> pd.DataFrame:
    """Load 1m Parquet → Resample เป็น 4H OHLCV"""
    parquet_path = DATA_DIR / f"{symbol}" / "1m.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}")
    
    df = pd.read_parquet(parquet_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    
    ohlcv = df.resample("4h").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()
    
    ohlcv = ohlcv.reset_index()
    ohlcv["timestamp"] = ohlcv["timestamp"].astype(str)
    return ohlcv


def compute_indicators(df: pd.DataFrame, cfg: TrendConfig) -> pd.DataFrame:
    df = df.copy()
    
    # Donchian Channel
    df["donchian_high"] = df["high"].rolling(cfg.donchian_period).max()
    df["donchian_low"] = df["low"].rolling(cfg.donchian_period).min()
    df["donchian_mid"] = (df["donchian_high"] + df["donchian_low"]) / 2
    
    # ATR
    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1))
        )
    )
    df["atr"] = df["tr"].rolling(cfg.atr_period).mean()
    
    # EMA 200 (Trend Filter)
    df["ema_200"] = df["close"].ewm(span=cfg.ema_period, adjust=False).mean()
    
    # Volume MA
    df["volume_ma"] = df["volume"].rolling(20).mean()
    
    # Proper Breakout Signals:
    # Long: Close > Donchian High (previous bar) + Price > EMA 200 + Volume > Avg
    # Short: Close < Donchian Low (previous bar) + Price < EMA 200 + Volume > Avg
    
    prev_high = df["donchian_high"].shift(1)
    prev_low = df["donchian_low"].shift(1)
    prev_mid = df["donchian_mid"].shift(1)
    
    df["signal_long"] = (
        (df["close"] > prev_high) &           # Close above previous high
        (df["close"] > df["ema_200"]) &       # Trend filter: above EMA 200
        (df["volume"] > df["volume_ma"]) &    # Volume confirmation
        (df["ema_200"] > df["ema_200"].shift(1))  # EMA sloping up
    )
    
    df["signal_short"] = (
        (df["close"] < prev_low) &            # Close below previous low
        (df["close"] < df["ema_200"]) &       # Trend filter: below EMA 200
        (df["volume"] > df["volume_ma"]) &    # Volume confirmation
        (df["ema_200"] < df["ema_200"].shift(1))  # EMA sloping down
    )
    
    return df


def run_trend_following_backtest(
    symbol: str,
    cfg: TrendConfig = None,
    verbose: bool = True
) -> dict:
    
    if cfg is None:
        cfg = TrendConfig()
    
    if verbose:
        print(f"🔄 Loading {symbol} ({cfg.timeframe})...")
    
    df = load_4h_data(symbol)
    total_rows = len(df)
    
    if verbose:
        print(f"   Rows: {total_rows:,} ({total_rows*4/24:.0f} days)")
    
    df = compute_indicators(df, cfg)
    
    capital = 10000.0
    equity = capital
    position: Optional[dict] = None
    trades: List[Trade] = []
    
    timestamps = df["timestamp"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    donchian_highs = df["donchian_high"].values
    donchian_lows = df["donchian_low"].values
    donchian_mids = df["donchian_mid"].values
    atrs = df["atr"].values
    ema_200 = df["ema_200"].values
    sig_long = df["signal_long"].values
    sig_short = df["signal_short"].values
    
    if verbose:
        print(f"   Running backtest...")
    
    for i in range(1, total_rows):
        ts = str(timestamps[i])
        price = closes[i]
        high = highs[i]
        low = lows[i]
        atr = atrs[i] if not np.isnan(atrs[i]) else 0
        
        if np.isnan(donchian_mids[i]) or atr == 0 or np.isnan(ema_200[i]):
            continue
        
        # ========= HAS POSITION =========
        if position is not None:
            side = position["side"]
            entry_price = position["entry_price"]
            trailing_stop = position["trailing_stop"]
            size_usd = position["size_usd"]
            
            # Update trailing stop
            if side == "LONG":
                new_trail = high - cfg.trailing_stop_multiplier * atr
                if new_trail > trailing_stop:
                    trailing_stop = new_trail
            else:
                new_trail = low + cfg.trailing_stop_multiplier * atr
                if new_trail < trailing_stop:
                    trailing_stop = new_trail
            
            exit_price = None
            exit_reason = ""
            
            if side == "LONG":
                if low <= trailing_stop:
                    exit_price = trailing_stop
                    exit_reason = "TRAILING_STOP"
                elif price < donchian_mids[i]:
                    exit_price = price
                    exit_reason = "MID_BAND"
            else:
                if high >= trailing_stop:
                    exit_price = trailing_stop
                    exit_reason = "TRAILING_STOP"
                elif price > donchian_mids[i]:
                    exit_price = price
                    exit_reason = "MID_BAND"
            
            if exit_price is not None:
                qty = size_usd / entry_price
                fee = size_usd * cfg.fee_rate * 2
                
                if side == "LONG":
                    gross = (exit_price - entry_price) * qty
                else:
                    gross = (entry_price - exit_price) * qty
                
                pnl = gross * cfg.leverage - fee
                equity += pnl
                
                entry_dt = pd.Timestamp(position["entry_time"])
                exit_dt = pd.Timestamp(ts)
                holding_hours = (exit_dt - entry_dt).total_seconds() / 3600
                
                trades.append(Trade(
                    symbol=symbol,
                    side=side,
                    entry_time=position["entry_time"],
                    entry_price=entry_price,
                    exit_time=ts,
                    exit_price=exit_price,
                    size_usd=size_usd,
                    pnl_usd=round(pnl, 2),
                    holding_hours=round(holding_hours, 1),
                    exit_reason=exit_reason
                ))
                
                position = None
            else:
                position["trailing_stop"] = trailing_stop
        
        # ========= NO POSITION → CHECK SIGNAL =========
        else:
            if sig_long[i] and equity > 0:
                entry_price = closes[i]
                atr_val = atrs[i]
                trailing_stop = entry_price - cfg.trailing_stop_multiplier * atr_val
                position = {
                    "side": "LONG",
                    "entry_price": entry_price,
                    "entry_time": ts,
                    "trailing_stop": trailing_stop,
                    "size_usd": cfg.position_size_usd
                }
            
            elif sig_short[i] and equity > 0:
                entry_price = closes[i]
                atr_val = atrs[i]
                trailing_stop = entry_price + cfg.trailing_stop_multiplier * atr_val
                position = {
                    "side": "SHORT",
                    "entry_price": entry_price,
                    "entry_time": ts,
                    "trailing_stop": trailing_stop,
                    "size_usd": cfg.position_size_usd
                }
    
    # Force close
    if position is not None:
        exit_price = closes[-1]
        qty = position["size_usd"] / position["entry_price"]
        fee = position["size_usd"] * cfg.fee_rate * 2
        
        if position["side"] == "LONG":
            gross = (exit_price - position["entry_price"]) * qty
        else:
            gross = (position["entry_price"] - exit_price) * qty
        
        pnl = gross * cfg.leverage - fee
        equity += pnl
        
        trades.append(Trade(
            symbol=symbol,
            side=position["side"],
            entry_time=position["entry_time"],
            entry_price=position["entry_price"],
            exit_time=str(timestamps[-1]),
            exit_price=exit_price,
            size_usd=position["size_usd"],
            pnl_usd=round(pnl, 2),
            holding_hours=0,
            exit_reason="END_OF_DATA"
        ))
    
    # Stats
    trades_df = pd.DataFrame([vars(t) for t in trades])
    
    if len(trades_df) == 0:
        return {"error": "No trades", "stats": {}}
    
    wins = trades_df[trades_df["pnl_usd"] > 0]
    losses = trades_df[trades_df["pnl_usd"] <= 0]
    
    total_pnl = trades_df["pnl_usd"].sum()
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / len(trades_df) * 100 if len(trades_df) > 0 else 0
    
    avg_win = wins["pnl_usd"].mean() if win_count > 0 else 0
    avg_loss = losses["pnl_usd"].mean() if loss_count > 0 else 0
    
    gross_profit = wins["pnl_usd"].sum() if win_count > 0 else 0
    gross_loss = abs(losses["pnl_usd"].sum()) if loss_count > 0 else 1
    profit_factor = gross_profit / gross_loss
    
    equity_curve = [capital]
    for t in trades:
        equity_curve.append(equity_curve[-1] + t.pnl_usd)
    equity_curve = np.array(equity_curve)
    peak = np.maximum.accumulate(equity_curve)
    dd = (peak - equity_curve) / peak * 100
    max_dd = dd.max()
    
    trade_returns = trades_df["pnl_usd"] / capital
    if trade_returns.std() > 0:
        sharpe = trade_returns.mean() / trade_returns.std() * np.sqrt(252 * 6 / max(len(trades_df), 1))  # 4H = 6 periods/day
    else:
        sharpe = 0
    
    avg_hold = trades_df["holding_hours"].mean()
    
    stats = {
        "total_trades": len(trades_df),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 2),
        "total_pnl_usd": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / capital * 100, 2),
        "final_equity": round(equity, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe, 2),
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "avg_holding_hours": round(avg_hold, 1),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
    }
    
    if verbose:
        print_stats(stats, symbol)
    
    return {
        "stats": stats,
        "trades_df": trades_df,
        "equity_curve": equity_curve,
    }


def print_stats(stats: dict, symbol: str):
    print(f"\n{'='*60}")
    print(f"📈 {symbol} — Trend Following (Donchian 4H + EMA200 Filter)")
    print(f"{'='*60}")
    print(f"   Trades:      {stats['total_trades']:,}")
    print(f"   Win Rate:    {stats['win_rate']:.2f}% ({stats['win_count']}W / {stats['loss_count']}L)")
    print(f"   PnL:         ${stats['total_pnl_usd']:+,.2f} ({stats['total_pnl_pct']:+.2f}%)")
    print(f"   Final Equity: ${stats['final_equity']:+,.2f}")
    print(f"   Max DD:      {stats['max_drawdown_pct']:.2f}%")
    print(f"   Profit Factor: {stats['profit_factor']:.2f}")
    print(f"   Sharpe:      {stats['sharpe_ratio']:.2f}")
    print(f"   Avg Win:     ${stats['avg_win_usd']:+,.2f}")
    print(f"   Avg Loss:    ${stats['avg_loss_usd']:+,.2f}")
    print(f"   Avg Hold:    {stats['avg_holding_hours']:.1f} hrs")
    print(f"{'='*60}\n")


def generate_comparison_report(
    trend_stats: dict,
    tailek_stats: dict,
    symbol: str,
    output_path: str = None
):
    
    ts = trend_stats
    tl = tailek_stats
    
    if output_path is None:
        output_path = REPORT_DIR / f"comparison_{symbol}.html"
    
    REPORT_DIR.mkdir(exist_ok=True)
    
    trend_eq = trend_stats.get("equity_curve", [])
    tl_eq = tailek_stats.get("equity_curve", [])
    
    html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strategy Comparison — {symbol}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #58a6ff; text-align: center; margin: 30px 0; }}
        h2 {{ color: #79c0ff; margin: 20px 0 10px; border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px 16px; text-align: center; border-bottom: 1px solid #30363d; }}
        th {{ background: #161b22; color: #58a6ff; }}
        td {{ background: #161b22; }}
        .better {{ color: #3fb950; font-weight: bold; }}
        .worse {{ color: #f85149; }}
        .chart-container {{ background: #161b22; border-radius: 8px; padding: 20px; margin: 20px 0; height: 350px; }}
        .winner-box {{ background: #0d1117; border: 2px solid #3fb950; border-radius: 12px; padding: 20px; margin: 20px 0; text-align: center; }}
        .winner-box h3 {{ color: #3fb950; margin-bottom: 10px; }}
        .winner-box p {{ color: #c9d1d9; }}
    </style>
</head>
<body>
<div class="container">
    <h1>⚔️ Strategy Comparison — {symbol}</h1>
    <p style="text-align:center;color:#8b949e;">Trend Following (Donchian 4H + EMA200) vs Mean Reversion (ตาเล็ก DCA) | 3 Year Backtest</p>

    <h2>📊 Head-to-Head</h2>
    <table>
        <tr>
            <th>Metric</th>
            <th>📈 Trend Following</th>
            <th>📉 ตาเล็ก (DCA)</th>
            <th>Winner</th>
        </tr>
        <tr>
            <td>Total Trades</td>
            <td>{ts.get('total_trades', 0):,}</td>
            <td>{tl.get('total_trades', 0):,}</td>
            <td>—</td>
        </tr>
        <tr>
            <td>Win Rate</td>
            <td>{ts.get('win_rate', 0):.1f}%</td>
            <td>{tl.get('win_rate', 0):.1f}%</td>
            <td class="{'better' if tl.get('win_rate',0) > ts.get('win_rate',0) else 'worse'}">{'ตาเล็ก' if tl.get('win_rate',0) > ts.get('win_rate',0) else 'Trend'}</td>
        </tr>
        <tr>
            <td>Total PnL</td>
            <td class="{'better' if ts.get('total_pnl_usd',0) > 0 else 'worse'}">${ts.get('total_pnl_usd', 0):+,.2f}</td>
            <td class="{'better' if tl.get('total_pnl_usd',0) > 0 else 'worse'}">${tl.get('total_pnl_usd', 0):+,.2f}</td>
            <td class="better">{'Trend' if ts.get('total_pnl_usd',0) > tl.get('total_pnl_usd',0) else 'ตาเล็ก'}</td>
        </tr>
        <tr>
            <td>Max Drawdown</td>
            <td class="{'better' if ts.get('max_drawdown_pct',100) < tl.get('max_drawdown_pct',100) else 'worse'}">{ts.get('max_drawdown_pct', 0):.2f}%</td>
            <td class="{'better' if tl.get('max_drawdown_pct',100) < ts.get('max_drawdown_pct',100) else 'worse'}">{tl.get('max_drawdown_pct', 0):.2f}%</td>
            <td class="better">{'Trend' if ts.get('max_drawdown_pct',100) < tl.get('max_drawdown_pct',100) else 'ตาเล็ก'}</td>
        </tr>
        <tr>
            <td>Profit Factor</td>
            <td>{ts.get('profit_factor', 0):.2f}</td>
            <td>{tl.get('profit_factor', 0):.2f}</td>
            <td class="better">{'Trend' if ts.get('profit_factor',0) > tl.get('profit_factor',0) else 'ตาเล็ก'}</td>
        </tr>
        <tr>
            <td>Sharpe Ratio</td>
            <td>{ts.get('sharpe_ratio', 0):.2f}</td>
            <td>{tl.get('sharpe_ratio', 0):.2f}</td>
            <td class="better">{'Trend' if ts.get('sharpe_ratio',0) > tl.get('sharpe_ratio',0) else 'ตาเล็ก'}</td>
        </tr>
        <tr>
            <td>Final Equity</td>
            <td class="{'better' if ts.get('final_equity',0) > tl.get('final_equity',0) else 'worse'}">${ts.get('final_equity', 0):+,.2f}</td>
            <td class="{'better' if tl.get('final_equity',0) > ts.get('final_equity',0) else 'worse'}">${tl.get('final_equity', 0):+,.2f}</td>
            <td class="better">{'Trend' if ts.get('final_equity',0) > tl.get('final_equity',0) else 'ตาเล็ก'}</td>
        </tr>
        <tr>
            <td>Avg Holding</td>
            <td>{ts.get('avg_holding_hours', 0):.1f} hrs</td>
            <td>{tl.get('avg_holding_hours', 0):.1f} hrs</td>
            <td>—</td>
        </tr>
    </table>

    <div class="winner-box">
        <h3>🏆 Overall Winner: {'📈 Trend Following' if ts.get('total_pnl_usd',0) > tl.get('total_pnl_usd',0) else '📉 ตาเล็ก DCA'}</h3>
        <p>Total PnL: ${max(ts.get('total_pnl_usd',0), tl.get('total_pnl_usd',0)):+,.2f} | 
           Max DD: {min(ts.get('max_drawdown_pct',100), tl.get('max_drawdown_pct',100)):.2f}% | 
           Profit Factor: {max(ts.get('profit_factor',0), tl.get('profit_factor',0)):.2f}</p>
    </div>

    <h2>📈 Equity Curves</h2>
    <div class="chart-container"><canvas id="equityChart"></canvas></div>

    <div style="text-align:center;color:#484f58;margin-top:40px;">
        <p>Generated by Crypto Backtest Engine v2.0</p>
    </div>

<script>
const trendEquity = {json.dumps([round(float(x), 2) for x in trend_eq])};
const tlEquity = {json.dumps([round(float(x), 2) for x in tl_eq])};
const GREEN = '#3fb950';
const RED = '#f85149';
const GRID = '#30363d';
const GRAY = '#8b949e';

new Chart(document.getElementById('equityChart').getContext('2d'), {{
    type: 'line',
    data: {{
        labels: Array.from({{length: Math.max(trendEquity.length, tlEquity.length)}}, (_, i) => i),
        datasets: [{{
            label: '📈 Trend Following',
            data: trendEquity,
            borderColor: GREEN,
            backgroundColor: 'rgba(63,185,80,0.1)',
            fill: false,
            tension: 0.1,
            pointRadius: 0,
            borderWidth: 2
        }}, {{
            label: '📉 ตาเล็ก DCA',
            data: tlEquity,
            borderColor: RED,
            backgroundColor: 'rgba(248,81,73,0.1)',
            fill: false,
            tension: 0.1,
            pointRadius: 0,
            borderWidth: 2
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
            legend: {{ labels: {{ color: '#c9d1d9' }} }},
            title: {{ display: true, color: '#c9d1d9', text: 'Equity Curve Comparison' }}
        }},
        scales: {{
            x: {{ grid: {{ color: GRID }}, ticks: {{ color: GRAY, maxTicksLimit: 10 }} }},
            y: {{ grid: {{ color: GRID }}, ticks: {{ color: GRAY }} }}
        }}
    }}
}});
</script>
</body>
</html>"""
    
    output_path = Path(output_path)
    output_path.write_text(html, encoding="utf-8")
    print(f"Comparison report saved: {output_path}")


if __name__ == "__main__":
    cfg = TrendConfig(
        donchian_period=20,
        atr_period=14,
        ema_period=200,
        trailing_stop_multiplier=2.0,
        position_size_usd=2000.0,
        leverage=5,
        fee_rate=0.0002,
        timeframe="4H"
    )
    
    result = run_trend_following_backtest("BTCUSDT", cfg, verbose=True)
    
    if "error" not in result:
        generate_comparison_report(
            trend_stats=result["stats"],
            tailek_stats={
                "total_trades": 2709,
                "win_rate": 100.0,
                "total_pnl_usd": 2485.39,
                "final_equity": 12485.39,
                "max_drawdown_pct": 0.0,
                "profit_factor": 999.0,
                "sharpe_ratio": 0.0,
                "avg_holding_hours": 0.7,
                "equity_curve": list(range(2710))
            },
            symbol="BTCUSDT"
        )