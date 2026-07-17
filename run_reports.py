#!/usr/bin/env python3
import sys
sys.path.insert(0, ".")
from backtest.runner import run_backtest, load_config
from analytics.report import generate_html_report

cfg = load_config()
symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "DOGEUSDT", "AXSUSDT", "1000LUNCUSDT"]

for sym in symbols:
    try:
        r = run_backtest(sym, cfg)
        generate_html_report(sym, r['stats'], r['equity_curve'], r['trades'])
    except Exception as e:
        print(f"ERROR {sym}: {e}")

print("\nDONE!")
