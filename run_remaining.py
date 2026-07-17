#!/usr/bin/env python3
import sys
sys.path.insert(0, ".")

from backtest.runner import run_backtest, load_config
from analytics.report import generate_html_report

cfg = load_config()
for sym in ["AXSUSDT", "1000LUNCUSDT"]:
    try:
        r = run_backtest(sym, cfg)
        generate_html_report(sym, r['stats'], r['equity_curve'], r['trades'])
        print(f"✅ {sym}: Win {r['stats']['win_rate']:.2f}% | PnL ${r['stats']['total_pnl_usd']:,.2f} | DD {r['stats']['max_drawdown_pct']:.2f}% | Trades {r['stats']['total_trades']:,}")
    except Exception as e:
        print(f"❌ {sym}: {e}")
