#!/usr/bin/env python3
"""
main.py — Entry Point: รัน Backtest สำหรับทุก Symbol
"""
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from backtest.runner import load_config, run_backtest, print_stats


def main():
    """รัน backtest สำหรับทุก symbol ที่มีในโฟลเดอร์ parquet"""
    cfg = load_config()
    parquet_dir = Path("data/parquet")
    symbols = [d.name for d in parquet_dir.iterdir() if d.is_dir()]

    if not symbols:
        print("❌ ไม่พบโฟลเดอร์ Parquet ใน data/parquet/")
        print("   รัน `python -m data.store` ก่อน")
        return

    print(f"📊 Found {len(symbols)} symbols: {', '.join(symbols)}")
    print(f"   Strategy: {cfg.get('strategy', {}).get('name', 'Unknown')}")
    print(f"   Capital: ${cfg.get('strategy', {}).get('initial_capital', 0):,.2f}")
    print(f"   Size/trade: ${cfg.get('strategy', {}).get('size_per_trade_usd', 0):,.2f}")

    results = {}

    for symbol in sorted(symbols):
        try:
            result = run_backtest(symbol, cfg)
            results[symbol] = result
            print_stats(result["stats"], symbol)
        except Exception as e:
            print(f"❌ Error {symbol}: {e}")

    # สรุปรวม
    if results:
        print("\n" + "=" * 60)
        print("📋 SUMMARY — ทุก Symbol")
        print("=" * 60)
        for symbol, r in results.items():
            s = r["stats"]
            print(f"   {symbol:20s} | Trades: {s['total_trades']:5d} | WinRate: {s['win_rate']:.2f}% | PnL: ${s['total_pnl_usd']:10,.2f} | DD: {s['max_drawdown_pct']:.2f}%")
        print("=" * 60)

        # บันทึก trade logs
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        for symbol, r in results.items():
            trades_df = r["trades"]
            trades_df.to_csv(output_dir / f"{symbol}_trades.csv", index=False)

            equity_df = r["equity_curve"]
            equity_df.to_csv(output_dir / f"{symbol}_equity.csv", index=False)

            print(f"💾 Saved {output_dir}/{symbol}_trades.csv")
            print(f"💾 Saved {output_dir}/{symbol}_equity.csv")

    print("\n✅ Backtest complete!")


if __name__ == "__main__":
    main()