"""
run_5m.py — Backtest DCA (ตาเล็ก) บน TF 5m
Resample ข้อมูล 1m → 5m แล้วรัน Strategy เดิม
"""
import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm

from data.store import load_parquet
from engine.indicators import compute_rsi, compute_candle_features, detect_candle_patterns
from engine.position import Position
from backtest.portfolio import Portfolio, TradeLog


CONFIG_DIR = Path(__file__).parent / "config"
DATA_DIR = Path(__file__).parent / "data" / "parquet"


def load_5m_data(symbol):
    """Load 1m → Resample เป็น 5m"""
    parquet_path = DATA_DIR / f"{symbol}" / "1m.parquet"
    df = pd.read_parquet(parquet_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()

    ohlcv = df.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna().reset_index()
    
    ohlcv["timestamp"] = ohlcv["timestamp"].astype(str)
    return ohlcv


def maker_price(price, side, offset_pct=0.05):
    offset = offset_pct / 100.0
    return price * (1.0 - offset) if side == "LONG" else price * (1.0 + offset)


def run_backtest_5m(symbol):
    with open(CONFIG_DIR / "strategy.yaml") as f:
        cfg = yaml.safe_load(f)

    strategy_cfg = cfg.get("strategy", {})
    signal_cfg = cfg.get("signal", {})
    order_cfg = cfg.get("order", {})
    position_cfg = cfg.get("position", {})

    capital = strategy_cfg.get("initial_capital", 10000.0)
    size_per_trade = strategy_cfg.get("size_per_trade_usd", 100.0)
    leverage = strategy_cfg.get("leverage", 3)
    
    position_cfg["leverage"] = leverage
    
    cooldown_minutes = position_cfg.get("cooldown_minutes", 5)
    max_cap = position_cfg.get("dca_max_cap_usd", 30000.0)
    fee_rate = order_cfg.get("fee_rate_maker", 0.02) / 100.0
    offset_pct = order_cfg.get("price_offset_percent", 0.05)
    long_timeout = position_cfg.get("long_timeout_minutes", 30)
    short_timeout = position_cfg.get("short_timeout_minutes", 120)
    monitor_interval = position_cfg.get("monitor_interval_minutes", 5)
    funding_rate_per_8h = position_cfg.get("funding_rate_per_8h", 0.01) / 100.0

    print(f"\n🔄 Loading {symbol} (5m TF)...")
    df = load_5m_data(symbol)
    total_rows = len(df)
    print(f"   Rows: {total_rows:,} ({total_rows * 5 / 60 / 24:.0f} days)")

    # Compute signals
    print("   Computing signals...")
    df["rsi"] = compute_rsi(df["close"].values, signal_cfg.get("rsi_period", 14))
    df = compute_candle_features(df)
    df = detect_candle_patterns(df)

    rsi_long = signal_cfg.get("rsi_long_threshold", 40.0)
    rsi_short = signal_cfg.get("rsi_short_threshold", 60.0)

    df["signal_long"] = (
        (df["rsi"] < rsi_long) &
        (~df["closes_at_low"]) &
        (~df["consec_high_5"]) &
        (~df["touch_pattern_3"])
    )
    df["signal_short"] = (
        (df["rsi"] > rsi_short) &
        (~df["consec_low_5"]) &
        (~df["touch_pattern_3_low"])
    )

    long_count = int(df["signal_long"].sum())
    short_count = int(df["signal_short"].sum())
    print(f"   Long: {long_count:,} | Short: {short_count:,}")

    # Simulate
    portfolio = Portfolio(initial_capital=capital)
    position = None
    active_order = None

    timestamps = df["timestamp"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    sig_long = df["signal_long"].values
    sig_short = df["signal_short"].values

    cooldown_remaining = 0
    funding_tick = 0
    monitor_tick = 0

    print(f"   Simulating ({total_rows:,} candles)...")
    progress = tqdm(total=total_rows, desc="   ", unit="candle", mininterval=5)

    for i in range(1, total_rows):
        ts = str(timestamps[i])
        price = closes[i]
        high = highs[i]
        low = lows[i]

        # Funding
        funding_tick += 1
        if funding_tick >= 96 and position and position.status == "OPEN":
            funding_per_unit = price * funding_rate_per_8h
            position.apply_funding(funding_per_unit * position.total_qty)
            funding_tick = 0

        # Cooldown
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            portfolio.update_equity(ts)
            progress.update(1)
            continue

        monitor_tick += 1
        monitor_triggered = monitor_tick >= monitor_interval
        if monitor_triggered:
            monitor_tick = 0

        # Has position
        if position is not None and position.status == "OPEN":
            position.update_time()
            side = position.side

            # Liquidation
            if position.check_liquidation(low if side == "LONG" else high):
                loss_usd = position.margin_used
                position.liquidate(ts, position.liquidation_price, fee_rate)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp, close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price, dca_count=position.dca_count,
                    pnl_usd=round(-loss_usd, 2), pnl_pct=-100.0,
                    fee_usd=round(position.total_fees_usd, 2),
                    holding_minutes=position.holding_time_minutes,
                    close_reason="LIQUIDATED",
                ))
                portfolio.update_equity(ts)
                position = None
                active_order = None
                cooldown_remaining = cooldown_minutes
                progress.update(1)
                continue

            # TP
            if side == "LONG" and high >= position.take_profit_price:
                exit_price = position.take_profit_price
                position.close(ts, exit_price, fee_rate)
                pnl = position.pnl(exit_price)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp, close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price, dca_count=position.dca_count,
                    pnl_usd=round(pnl, 2), pnl_pct=round(pnl / position.total_size_usd * 100, 4),
                    fee_usd=round(position.total_fees_usd, 2),
                    holding_minutes=position.holding_time_minutes,
                    close_reason="TP",
                ))
                portfolio.update_equity(ts)
                position = None
                active_order = None
                cooldown_remaining = cooldown_minutes
                progress.update(1)
                continue

            if side == "SHORT" and low <= position.take_profit_price:
                exit_price = position.take_profit_price
                position.close(ts, exit_price, fee_rate)
                pnl = position.pnl(exit_price)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp, close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price, dca_count=position.dca_count,
                    pnl_usd=round(pnl, 2), pnl_pct=round(pnl / position.total_size_usd * 100, 4),
                    fee_usd=round(position.total_fees_usd, 2),
                    holding_minutes=position.holding_time_minutes,
                    close_reason="TP",
                ))
                portfolio.update_equity(ts)
                position = None
                active_order = None
                cooldown_remaining = cooldown_minutes
                progress.update(1)
                continue

            # Monitor
            if monitor_triggered:
                timeout_hit = (side == "LONG" and position.holding_time_minutes >= long_timeout) or \
                             (side == "SHORT" and position.holding_time_minutes >= short_timeout)
                if timeout_hit:
                    position.merge_orders(ts, fee_rate)
                    active_order = {
                        "price": position.take_profit_price,
                        "side": "SELL" if side == "LONG" else "BUY",
                        "is_tp": True,
                    }

            # DCA
            if position.check_dca_trigger(low if side == "LONG" else high):
                dca_price = maker_price(price, side, offset_pct)
                position.add_trade(ts, "DCA", dca_price, size_per_trade, fee_rate)
                position.update_liquidation_price()
                active_order = {
                    "price": position.take_profit_price,
                    "side": "SELL" if side == "LONG" else "BUY",
                    "is_tp": True,
                }

            # Order loop
            if active_order and not active_order.get("is_tp"):
                order_p = active_order["price"]
                if side == "LONG":
                    if low <= order_p:
                        position.add_trade(ts, "OPEN", order_p, size_per_trade, fee_rate)
                        position.update_liquidation_price()
                        active_order = {"price": position.take_profit_price, "side": "SELL", "is_tp": True}
                    else:
                        active_order = None
                else:
                    if high >= order_p:
                        position.add_trade(ts, "OPEN", order_p, size_per_trade, fee_rate)
                        position.update_liquidation_price()
                        active_order = {"price": position.take_profit_price, "side": "BUY", "is_tp": True}
                    else:
                        active_order = None

            portfolio.update_equity(ts)
            progress.update(1)
            continue

        # No position → Signal
        if sig_long[i]:
            order_price = maker_price(price, "LONG", offset_pct)
            if low <= order_price:
                pos = Position(symbol, "LONG", size_per_trade, position_cfg)
                pos.add_trade(ts, "OPEN", order_price, size_per_trade, fee_rate)
                position = pos
                active_order = {"price": position.take_profit_price, "side": "SELL", "is_tp": True}
            else:
                active_order = {"price": order_price, "side": "LONG", "is_tp": False}
            portfolio.update_equity(ts)

        elif sig_short[i]:
            order_price = maker_price(price, "SHORT", offset_pct)
            if high >= order_price:
                pos = Position(symbol, "SHORT", size_per_trade, position_cfg)
                pos.add_trade(ts, "OPEN", order_price, size_per_trade, fee_rate)
                position = pos
                active_order = {"price": position.take_profit_price, "side": "BUY", "is_tp": True}
            else:
                active_order = {"price": order_price, "side": "SHORT", "is_tp": False}
            portfolio.update_equity(ts)

        else:
            portfolio.update_equity(ts)

        progress.update(1)

    progress.close()

    # Force close
    if position and position.status == "OPEN":
        last_ts = str(timestamps[-1])
        last_price = closes[-1]
        position.close(last_ts, last_price, fee_rate)
        pnl = position.pnl(last_price)
        portfolio.record_trade(TradeLog(
            symbol=symbol, side=position.side,
            open_time=position.records[0].timestamp, close_time=last_ts,
            ep=position.entry_price, bep=position.bep,
            tp=position.take_profit_price, dca_count=position.dca_count,
            pnl_usd=round(pnl, 2),
            pnl_pct=round(pnl / position.total_size_usd * 100, 4) if position.total_size_usd > 0 else 0.0,
            fee_usd=round(position.total_fees_usd, 2),
            holding_minutes=position.holding_time_minutes,
            close_reason="END_OF_DATA",
        ))

    return portfolio


if __name__ == "__main__":
    symbols = ["BTCUSDT", "DOGEUSDT"]
    
    for sym in symbols:
        portfolio = run_backtest_5m(sym)
        
        normal_trades = [t for t in portfolio.trade_logs if t.close_reason != "END_OF_DATA"]
        end_data_trades = [t for t in portfolio.trade_logs if t.close_reason == "END_OF_DATA"]
        
        normal_pnl = sum(t.pnl_usd for t in normal_trades) if normal_trades else 0
        normal_win = sum(1 for t in normal_trades if t.pnl_usd > 0) if normal_trades else 0
        normal_count = len(normal_trades)
        
        end_pnl = sum(t.pnl_usd for t in end_data_trades) if end_data_trades else 0
        end_count = len(end_data_trades)
        
        total_pnl = sum(t.pnl_usd for t in portfolio.trade_logs)
        total_trades = len(portfolio.trade_logs)
        win_count = sum(1 for t in portfolio.trade_logs if t.pnl_usd > 0)
        
        max_dca = max((t.dca_count for t in portfolio.trade_logs), default=0)
        avg_dca = sum(t.dca_count for t in portfolio.trade_logs) / total_trades if total_trades else 0
        
        print(f"\n{'='*60}")
        print(f"📊 {sym} (5m TF)")
        print(f"{'='*60}")
        print(f"   Total Trades:  {total_trades:,}")
        print(f"   Win Rate:      {win_count/total_trades*100:.2f}% ({win_count}W / {total_trades-win_count}L)")
        print(f"   Total PnL:     ${total_pnl:+,.2f}")
        print(f"   Max DCA:       {max_dca} (ทุนสูงสุดที่ใช้: ${max_dca * 100 + 100:,.0f})")
        print(f"   Avg DCA:       {avg_dca:.1f}")
        print(f"   Closed PnL:    ${normal_pnl:+,.2f} ({normal_count} trades)")
        print(f"   END_OF_DATA:   ${end_pnl:+,.2f} ({end_count} trades)")
        print(f"{'='*60}")

    print(f"\n\n📊 FINAL COMPARISON:")
    print(f"   {'TF':<8} {'BTC PnL':<15} {'DOGE PnL':<15} {'Total':<15} {'Max DCA (USD)'}")
    print(f"   {'-'*70}")
