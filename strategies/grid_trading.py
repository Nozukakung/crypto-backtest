"""
strategies/grid_trading.py — Grid Trading Backtest v1.0
- ระบบ Neutral Grid: วาง Buy/Sell grid lines ครอบคลุมพื้นที่ตลาด
- ทำกำไรจาก volatility ฟันปลาโดยไม่ต้องเดาทิศทาง
- ปลอดภัยกว่า ถือเป็นเครื่องจักรทำเงินช่วง Sideway
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

DATA_DIR = Path(__file__).parent.parent / "data" / "parquet"
REPORT_DIR = Path(__file__).parent.parent / "reports"


@dataclass
class GridConfig:
    lower_price: float = 40000.0     # ขอบล่างของกริด
    upper_price: float = 90000.0     # ขอบบนของกริด
    grid_count: int = 50             # จำนวนกริต (จำนวนไม้)
    investment: float = 10000.0      # ทุนเริ่มต้น (USD)
    leverage: int = 5                # Leverage 5x
    fee_rate: float = 0.0002         # Fee 0.02%


@dataclass
class GridLog:
    timestamp: str
    action: str  # BUY / SELL
    price: float
    qty: float
    profit: float
    total_profit: float


def run_grid_backtest(symbol: str, cfg: GridConfig = None, verbose: bool = True) -> dict:
    if cfg is None:
        cfg = GridConfig()
        
    if verbose:
        print(f"🔄 Loading {symbol} for Grid Backtest...")
        
    parquet_path = DATA_DIR / f"{symbol}" / "1m.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}")
        
    df = pd.read_parquet(parquet_path)
    
    # Grid lines spacing
    grid_prices = np.linspace(cfg.lower_price, cfg.upper_price, cfg.grid_count)
    grid_spacing = grid_prices[1] - grid_prices[0]
    
    # Money per grid level
    capital_per_grid = cfg.investment / cfg.grid_count
    
    # Initialize grids
    # active_orders = list of prices where we have buy limit or sell limit
    # long_positions: list of buy matches. When price hits a grid line above, we close one and take profit.
    # short_positions: list of sell matches. When price hits a grid line below, we close one and take profit.
    
    long_positions = []  # List of entry prices
    short_positions = []
    
    total_realized_profit = 0.0
    trades_count = 0
    trade_logs: List[GridLog] = []
    
    timestamps = df["timestamp"].values
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    
    # Find initial price index in grids
    start_price = closes[0]
    
    # We place buy limit orders below start_price
    # and sell limit orders above start_price
    active_buys = {p: True for p in grid_prices if p < start_price}
    active_sells = {p: True for p in grid_prices if p > start_price}
    
    if verbose:
        print(f"   Grids initialized. Buys below {start_price:.0f}: {len(active_buys)}, Sells above: {len(active_sells)}")
        print(f"   Simulating {len(df):,} candles...")
        
    # We sample index to run faster (take every 5th minute for grid is more than enough)
    step = 5
    for i in range(0, len(closes), step):
        ts = str(timestamps[i])
        price = closes[i]
        high = highs[i]
        low = lows[i]
        
        # Check Buys (Low price triggered)
        for buy_p in list(active_buys.keys()):
            if low <= buy_p:
                # Match BUY order!
                qty = (capital_per_grid * cfg.leverage) / buy_p
                long_positions.append({"entry_price": buy_p, "qty": qty})
                
                # Remove this buy order
                del active_buys[buy_p]
                
                # Place corresponding SELL order 1 level above
                sell_target = buy_p + grid_spacing
                if sell_target <= cfg.upper_price:
                    active_sells[sell_target] = True
                    
                trades_count += 1
                trade_logs.append(GridLog(
                    timestamp=ts, action="BUY", price=buy_p, qty=qty, profit=0.0, total_profit=total_realized_profit
                ))
                
        # Check Sells (High price triggered)
        for sell_p in list(active_sells.keys()):
            if high >= sell_p:
                # Match SELL order!
                # If we have a long position to close, close it for profit (Take Profit)
                if long_positions:
                    # Close oldest long position
                    matched_long = long_positions.pop(0)
                    profit = (sell_p - matched_long["entry_price"]) * matched_long["qty"] - (sell_p * matched_long["qty"] * cfg.fee_rate * 2)
                    total_realized_profit += profit
                else:
                    # No long to close? Open a Short position
                    qty = (capital_per_grid * cfg.leverage) / sell_p
                    short_positions.append({"entry_price": sell_p, "qty": qty})
                    profit = 0.0
                    
                # Remove this sell order
                del active_sells[sell_p]
                
                # Place corresponding BUY order 1 level below
                buy_target = sell_p - grid_spacing
                if buy_target >= cfg.lower_price:
                    active_buys[buy_target] = True
                    
                trades_count += 1
                trade_logs.append(GridLog(
                    timestamp=ts, action="SELL", price=sell_p, qty=qty if not profit else matched_long["qty"], profit=profit, total_profit=total_realized_profit
                ))
                
        # If we have short positions and price drops to a buy level
        # we will match buy level, if we had shorts, we close them
        for buy_p in list(active_buys.keys()):
            if low <= buy_p and short_positions:
                matched_short = short_positions.pop(0)
                profit = (matched_short["entry_price"] - buy_p) * matched_short["qty"] - (buy_p * matched_short["qty"] * cfg.fee_rate * 2)
                total_realized_profit += profit
                
                del active_buys[buy_p]
                
                sell_target = buy_p + grid_spacing
                if sell_target <= cfg.upper_price:
                    active_sells[sell_target] = True
                    
                trades_count += 1
                # Replace the last buy log if we just matched it as a close
                trade_logs.append(GridLog(
                    timestamp=ts, action="BUY_CLOSE", price=buy_p, qty=matched_short["qty"], profit=profit, total_profit=total_realized_profit
                ))
                
    # Calculate paper asset value
    unrealized_pnl = 0.0
    last_price = closes[-1]
    
    for pos in long_positions:
        unrealized_pnl += (last_price - pos["entry_price"]) * pos["qty"]
    for pos in short_positions:
        unrealized_pnl += (pos["entry_price"] - last_price) * pos["qty"]
        
    final_equity = cfg.investment + total_realized_profit + unrealized_pnl
    
    stats = {
        "investment": cfg.investment,
        "final_equity": final_equity,
        "realized_profit": total_realized_profit,
        "unrealized_pnl": unrealized_pnl,
        "total_pnl_pct": (final_equity - cfg.investment) / cfg.investment * 100,
        "total_trades": trades_count,
        "average_grid_spacing": grid_spacing,
    }
    
    if verbose:
        print_stats(stats, symbol)
        
    return {"stats": stats, "logs": trade_logs}


def print_stats(stats: dict, symbol: str):
    print(f"\n{'='*60}")
    print(f"🤖 {symbol} — Neutral Grid Trading")
    print(f"{'='*60}")
    print(f"   Initial Investment: ${stats['investment']:,.2f}")
    print(f"   Final Equity:       ${stats['final_equity']:,.2f}")
    print(f"   Realized Profit:    ${stats['realized_profit']:+,.2f}")
    print(f"   Unrealized PnL:     ${stats['unrealized_pnl']:+,.2f}")
    print(f"   Total ROI:          {stats['total_pnl_pct']:+.2f}%")
    print(f"   Total Trades:       {stats['total_trades']:,}")
    print(f"   Grid Spacing:       ${stats['average_grid_spacing']:.2f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    cfg = GridConfig(
        lower_price=40000.0,
        upper_price=95000.0,
        grid_count=80,
        investment=10000.0,
        leverage=5,
        fee_rate=0.0002
    )
    run_grid_backtest("BTCUSDT", cfg)