"""
backtest/runner.py — Backtest v5 (Leverage 10x + Liquidation Check)
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


CONFIG_PATH = Path(__file__).parent.parent / "config" / "strategy.yaml"


def load_config(path=None):
    with open(path or str(CONFIG_PATH)) as f:
        return yaml.safe_load(f)


def maker_price(price, side, offset_pct=0.05):
    offset = offset_pct / 100.0
    if side == "LONG":
        return price * (1.0 - offset)
    else:
        return price * (1.0 + offset)


def run_backtest(symbol, cfg=None):
    if cfg is None:
        cfg = load_config()

    strategy_cfg = cfg.get("strategy", {})
    signal_cfg = cfg.get("signal", {})
    order_cfg = cfg.get("order", {})
    position_cfg = cfg.get("position", {})

    capital = strategy_cfg.get("initial_capital", 10000.0)
    size_per_trade = strategy_cfg.get("size_per_trade_usd", 100.0)
    leverage = strategy_cfg.get("leverage", 10)
    cooldown_minutes = position_cfg.get("cooldown_minutes", 5)
    max_cap = position_cfg.get("dca_max_cap_usd", 50000.0)
    fee_rate = order_cfg.get("fee_rate_maker", 0.02) / 100.0
    offset_pct = order_cfg.get("price_offset_percent", 0.05)
    long_timeout = position_cfg.get("long_timeout_minutes", 30)
    short_timeout = position_cfg.get("short_timeout_minutes", 120)
    monitor_interval = position_cfg.get("monitor_interval_minutes", 5)
    funding_rate_per_8h = position_cfg.get("funding_rate_per_8h", 0.01) / 100.0

    print(f"🔄 Loading {symbol}...")
    df = load_parquet(symbol)
    total_rows = len(df)
    print(f"   Rows: {total_rows:,}")

    # ====== Compute signals ======
    print(f"   Computing signals...")
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

    # ====== Simulate ======
    portfolio = Portfolio(initial_capital=capital)
    position = None
    active_order = None

    timestamps = df["timestamp"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    signal_long = df["signal_long"].values
    signal_short = df["signal_short"].values

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
        if funding_tick >= 480 and position and position.status == "OPEN":
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

        # ======= Has open position =======
        if position is not None and position.status == "OPEN":
            position.update_time()
            side = position.side

            # 1) Liquidation Check
            if position.check_liquidation(low if side == "LONG" else high):
                # โดน Liquidate! (เสีย Margin ที่ใช้ไปทั้งหมด)
                loss_usd = position.margin_used
                position.liquidate(ts, position.liquidation_price, fee_rate)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp, close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price, dca_count=position.dca_count,
                    pnl_usd=round(-loss_usd, 2),
                    pnl_pct=round(-100.0, 4),
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

            # 2) TP check
            if side == "LONG" and high >= position.take_profit_price:
                exit_price = position.take_profit_price
                position.close(ts, exit_price, fee_rate)
                pnl = position.pnl(exit_price)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp, close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price, dca_count=position.dca_count,
                    pnl_usd=round(pnl, 2),
                    pnl_pct=round(pnl / position.total_size_usd * 100, 4),
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
                    pnl_usd=round(pnl, 2),
                    pnl_pct=round(pnl / position.total_size_usd * 100, 4),
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

            # 3) Monitor (มัดรวม)
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

            # 4) DCA Check
            # อัปเดต liquidation price หลัง DCA
            if position.check_dca_trigger(low if side == "LONG" else high):
                dca_price = maker_price(price, side, offset_pct)
                position.add_trade(ts, "DCA", dca_price, size_per_trade, fee_rate)
                position.update_liquidation_price()
                active_order = {
                    "price": position.take_profit_price,
                    "side": "SELL" if side == "LONG" else "BUY",
                    "is_tp": True,
                }

            # 5) Order Loop ทุก 1 นาที
            if active_order and not active_order.get("is_tp"):
                order_p = active_order["price"]
                if side == "LONG":
                    if low <= order_p:
                        position.add_trade(ts, "OPEN", order_p, size_per_trade, fee_rate)
                        position.update_liquidation_price()
                        active_order = {
                            "price": position.take_profit_price,
                            "side": "SELL",
                            "is_tp": True,
                        }
                    else:
                        active_order = None
                else:
                    if high >= order_p:
                        position.add_trade(ts, "OPEN", order_p, size_per_trade, fee_rate)
                        position.update_liquidation_price()
                        active_order = {
                            "price": position.take_profit_price,
                            "side": "BUY",
                            "is_tp": True,
                        }
                    else:
                        active_order = None

            portfolio.update_equity(ts)
            progress.update(1)
            continue

        # ======= No position → เช็ค Signal (Long + Short) =======
        if signal_long[i]:
            order_price = maker_price(price, "LONG", offset_pct)
            if low <= order_price:
                pos = Position(symbol, "LONG", size_per_trade, position_cfg)
                pos.add_trade(ts, "OPEN", order_price, size_per_trade, fee_rate)
                position = pos
                active_order = {
                    "price": position.take_profit_price,
                    "side": "SELL",
                    "is_tp": True,
                }
            else:
                active_order = {
                    "price": order_price,
                    "side": "LONG",
                    "is_tp": False,
                }
            portfolio.update_equity(ts)

        elif signal_short[i]:
            order_price = maker_price(price, "SHORT", offset_pct)
            if high >= order_price:
                pos = Position(symbol, "SHORT", size_per_trade, position_cfg)
                pos.add_trade(ts, "OPEN", order_price, size_per_trade, fee_rate)
                position = pos
                active_order = {
                    "price": position.take_profit_price,
                    "side": "BUY",
                    "is_tp": True,
                }
            else:
                active_order = {
                    "price": order_price,
                    "side": "SHORT",
                    "is_tp": False,
                }
            portfolio.update_equity(ts)

        else:
            portfolio.update_equity(ts)

        progress.update(1)

    progress.close()

    # Force close remaining
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

    stats = portfolio.get_stats()
    return {
        "stats": stats,
        "equity_curve": portfolio.to_dataframe(),
        "trades": portfolio.trades_to_dataframe(),
    }


def print_stats(stats, symbol):
    print(f"\n{'='*60}")
    print(f"📈 {symbol} (Leverage 10x)")
    print(f"{'='*60}")
    if "error" in stats:
        print(f"   {stats['error']}")
        return
    print(f"   Trades:     {stats['total_trades']:,}")
    print(f"   Win Rate:   {stats['win_rate']:.2f}% (Wins: {stats['win_count']:,} | Losses: {stats['loss_count']:,})")
    print(f"   PnL:        ${stats['total_pnl_usd']:+,.2f} ({stats['total_pnl_pct']:+.2f}%)")
    print(f"   Equity:     ${stats['final_equity']:+,.2f}")
    print(f"   Max DD:     {stats['max_drawdown_pct']:.2f}% (${stats['max_drawdown_usd']:+,.2f})")
    print(f"   Fees:       ${stats['total_fees_usd']:+,.2f}")
    print(f"   Avg Hold:   {stats['avg_holding_minutes']:.0f} min")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    result = run_backtest(symbol)
    print_stats(result["stats"], symbol)