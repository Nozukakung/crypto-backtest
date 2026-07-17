#!/usr/bin/env python3
"""รัน backtest + สร้างรายงาน HTML สำหรับทุก symbol"""
import sys
sys.path.insert(0, ".")

from backtest.runner import run_backtest, load_config, print_stats
from analytics.report import generate_html_report

cfg = load_config()
symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "DOGEUSDT", "AXSUSDT", "1000LUNCUSDT"]

for sym in symbols:
    try:
        result = run_backtest(sym, cfg)
        print_stats(result["stats"], sym)
        generate_html_report(sym, result["stats"], result["equity_curve"], result["trades"])
    except Exception as e:
        print(f"ERROR {sym}: {e}")

print("\n DONE — ทุก symbol เสร็จแล้ว!")
