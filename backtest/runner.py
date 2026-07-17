"""
backtest/runner.py — Backtest หลัก (Optimized: vectorized signals + position simulation)
"""
import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm

from data.store import load_parquet
from engine.indicators import compute_rsi, compute_candle_features, detect_candle_patterns
from engine.position import Position
from engine.order import OrderManager, maker_price
from backtest.portfolio import Portfolio, TradeLog


CONFIG_PATH = Path(__file__).parent.parent / "config" / "strategy.yaml"


def load_config(path: str = None) -> dict:
    with open(path or str(CONFIG_PATH)) as f:
        return yaml.safe_load(f)


def run_backtest(symbol: str, cfg: dict = None) -> dict:
    if cfg is None:
        cfg = load_config()

    strategy_cfg = cfg.get("strategy", {})
    signal_cfg = cfg.get("signal", {})
    order_cfg = cfg.get("order", {})
    position_cfg = cfg.get("position", {})

    capital = strategy_cfg.get("initial_capital", 10000.0)
    size_per_trade = strategy_cfg.get("size_per_trade_usd", 100.0)

    print(f"🔄 Loading {symbol}...")
    df = load_parquet(symbol)
    total_rows = len(df)
    print(f"   Rows: {total_rows:,}")

    print(f"   Computing indicators & signals...")
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

    long_count = df["signal_long"].sum()
    short_count = df["signal_short"].sum()
    print(f"   Long signals:  {long_count:,} ({long_count/total_rows*100:.2f}%)")
    print(f"   Short signals: {short_count:,} ({short_count/total_rows*100:.2f}%)")

    portfolio = Portfolio(initial_capital=capital)
    position = None
    order_mgr = OrderManager(order_cfg)

    fee_rate = order_cfg.get("fee_rate_maker", 0.02) / 100.0
    offset_pct = order_cfg.get("price_offset_percent", 0.05)
    tp_pct = position_cfg.get("take_profit_above_bep_percent", 0.2) / 100.0
    dca_pct = position_cfg.get("dca_trigger_below_bep_percent", 0.3) / 100.0
    long_timeout = position_cfg.get("long_timeout_minutes", 30)
    short_timeout = position_cfg.get("short_timeout_minutes", 120)
    max_cap = position_cfg.get("dca_max_cap_usd", 50000.0)

    timestamps = df["timestamp"].values
    closes = df["close"].values
    signal_long = df["signal_long"].values
    signal_short = df["signal_short"].values

    print(f"   Simulating positions ({total_rows:,} candles)...")
    progress = tqdm(total=total_rows, desc="   Progress", unit="candle", mininterval=5)

    for i in range(1, total_rows):
        ts = str(timestamps[i])
        price = closes[i]

        # ── If position is open ──
        if position is not None and position.status == "OPEN":
            position.update_time()

            # 1) Check Take Profit
            side = position.side
            tp_hit = (side == "LONG" and price >= position.take_profit_price) or \
                     (side == "SHORT" and price <= position.take_profit_price)
            if tp_hit:
                position.close(ts, price, fee_rate, "TP")
                pnl = position.pnl(price)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp,
                    close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price,
                    dca_count=position.dca_count,
                    pnl_usd=pnl, pnl_pct=pnl / position.total_size_usd * 100 if position.total_size_usd else 0,
                    fee_usd=position.total_fees_usd,
                    holding_minutes=position.holding_time_minutes,
                    close_reason="TP",
                ))
                portfolio.update_equity(ts)
                position = None
                progress.update(1)
                continue

            # 2) Check Timeout → Force Exit (แก้บั๊ก ETH)
            timeout_hit = (side == "LONG" and position.holding_time_minutes >= long_timeout) or \
                         (side == "SHORT" and position.holding_time_minutes >= short_timeout)
            if timeout_hit:
                # Force close at current market price
                position.close(ts, price, fee_rate, "TIMEOUT")
                pnl = position.pnl(price)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp,
                    close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price,
                    dca_count=position.dca_count,
                    pnl_usd=pnl, pnl_pct=pnl / position.total_size_usd * 100 if position.total_size_usd else 0,
                    fee_usd=position.total_fees_usd,
                    holding_minutes=position.holding_time_minutes,
                    close_reason="TIMEOUT",
                ))
                portfolio.update_equity(ts)
                position = None
                progress.update(1)
                continue

            # 3) Check DCA
            dca_trigger = (side == "LONG" and price <= position.bep * (1 - dca_pct)) or \
                         (side == "SHORT" and price >= position.bep * (1 + dca_pct))
            if dca_trigger and position.total_size_usd + size_per_trade <= max_cap:
                dca_price = maker_price(price, side, offset_pct)
                position.add_trade(ts, "DCA", dca_price, size_per_trade, fee_rate)

            # 4) Update equity with unrealized PnL
            portfolio.update_equity(ts, position.pnl(price))
            progress.update(1)
            continue

        # ── No position → check signals ──
        if signal_long[i]:
            pos = Position(symbol, "LONG", size_per_trade, position_cfg)
            order_price = maker_price(price, "LONG", offset_pct)
            pos.add_trade(ts, "OPEN", order_price, size_per_trade, fee_rate)
            position = pos
            portfolio.update_equity(ts)

        elif signal_short[i]:
            pos = Position(symbol, "SHORT", size_per_trade, position_cfg)
            order_price = maker_price(price, "SHORT", offset_pct)
            pos.add_trade(ts, "OPEN", order_price, size_per_trade, fee_rate)
            position = pos
            portfolio.update_equity(ts)

        else:
            portfolio.update_equity(ts)

        progress.update(1)

    progress.close()

    # Force close any remaining position
    if position is not None and position.status == "OPEN":
        last_ts = str(timestamps[-1])
        last_price = closes[-1]
        position.close(last_ts, last_price, fee_rate, "END_OF_DATA")
        pnl = position.pnl(last_price)
        portfolio.record_trade(TradeLog(
            symbol=symbol, side=position.side,
            open_time=position.records[0].timestamp,
            close_time=last_ts,
            ep=position.entry_price, bep=position.bep,
            tp=position.take_profit_price,
            dca_count=position.dca_count,
            pnl_usd=pnl, pnl_pct=pnl / position.total_size_usd * 100 if position.total_size_usd else 0,
            fee_usd=position.total_fees_usd,
            holding_minutes=position.holding_time_minutes,
            close_reason="END_OF_DATA",
        ))

    return {
        "stats": portfolio.get_stats(),
        "equity_curve": portfolio.to_dataframe(),
        "trades": portfolio.trades_to_dataframe(),
    }


def print_stats(stats: dict, symbol: str):
    print(f"\n{'='*60}")
    print(f"📈 BACKTEST RESULTS — {symbol}")
    print(f"{'='*60}")
    if "error" in stats:
        print(f"   {stats['error']}")
        return
    print(f"   Total trades:        {stats['total_trades']:,}")
    print(f"   Win rate:            {stats['win_rate']:.2f}%")
    print(f"   Total PnL:           ${stats['total_pnl_usd']:,.2f} ({stats['total_pnl_pct']:+.2f}%)")
    print(f"   Final equity:        ${stats['final_equity']:,.2f}")
    print(f"   Max Drawdown:        {stats['max_drawdown_pct']:.2f}%")
    print(f"   Max Drawdown (USD):  ${stats['max_drawdown_usd']:,.2f}")
    print(f"   Total fees:          ${stats['total_fees_usd']:,.2f}")
    print(f"   Avg holding time:    {stats['avg_holding_minutes']:.0f} min")
    print(f"   Avg DCA count:       {stats['avg_dca_count']:.1f}")
    print(f"   Max DCA count:       {stats['max_dca_count']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    result = run_backtest(symbol)
    print_stats(result["stats"], symbol)