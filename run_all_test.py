#!/usr/bin/env python3
"""ทดสอบทุกเหรียญ + รายงานละเอียด"""
import sys
sys.path.insert(0, "/home/jakkrit/crypto-backtest")

from backtest.runner import run_backtest, load_config
from data.store import load_parquet
from engine.indicators import compute_rsi, compute_candle_features, detect_candle_patterns

cfg = load_config()
symbols = ["BTCUSDT", "DOGEUSDT", "BNBUSDT", "ETHUSDT", "AXSUSDT"]

header = f"{'เหรียญ':<10} | {'Win Rate':>9} | {'PnL ($)':>12} | {'Max DD':>8} | {'Trades':>8} | {'Avg PnL':>10} | {'Signal%':>8}"
sep = "=" * len(header)
print(sep)
print(header)
print(sep)

total_pnl = 0
total_dd = 0
total_trades = 0

for sym in symbols:
    try:
        df = load_parquet(sym)
        df["rsi"] = compute_rsi(df["close"].values, cfg["signal"].get("rsi_period", 14))
        df = compute_candle_features(df)
        df = detect_candle_patterns(df)
        rsi_long = cfg["signal"].get("rsi_long_threshold", 35.0)
        rsi_short = cfg["signal"].get("rsi_short_threshold", 65.0)
        sig_long = ((df["rsi"] < rsi_long) & (~df["closes_at_low"]) & (~df["consec_high_5"]) & (~df["touch_pattern_3"])).sum()
        sig_short = ((df["rsi"] > rsi_short) & (~df["consec_low_5"]) & (~df["touch_pattern_3_low"])).sum()
        signal_rate = (sig_long + sig_short) / len(df) * 100

        r = run_backtest(sym, cfg)
        s = r["stats"]
        pnl = s["total_pnl_usd"]
        dd = s["max_drawdown_pct"]
        trades = s["total_trades"]
        win_pct = s["win_rate"]
        avg_pnl = pnl / trades if trades > 0 else 0

        status = "✅" if pnl > 0 else "❌"
        print(f"{sym:<10} | {win_pct:>7.2f}% | ${pnl:>9,.2f} | {dd:>6.2f}% | {trades:>7,} | ${avg_pnl:>+7,.2f} | {signal_rate:>6.2f}% {status}")

        total_pnl += pnl
        total_dd = max(total_dd, dd)
        total_trades += trades

    except Exception as e:
        print(f"{sym:<10} | {'ERROR':>9} | {str(e)[:40]:>12}")

print(sep)
print(f"{'TOTAL':<10} | {'':>9} | ${total_pnl:>9,.2f} | {total_dd:>6.2f}% | {total_trades:>7,}")
print(sep)
print(f"\n🎯 Config: {cfg['strategy']['leverage']}x | Size ${cfg['strategy']['size_per_trade_usd']} | RSI {cfg['signal']['rsi_long_threshold']}/{cfg['signal']['rsi_short_threshold']} | DCA {cfg['position']['dca_trigger_below_bep_percent']}% | TP {cfg['position']['take_profit_above_bep_percent']}%")
print(f"💰 ROI: {total_pnl/cfg['strategy']['initial_capital']*100:.2f}% | DD: {total_dd:.2f}% | Trades: {total_trades:,}")
