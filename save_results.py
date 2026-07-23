#!/usr/bin/env python3
"""
save_results.py — บันทึกผลลัพธ์ Backtest เป็น JSON + CSV
รันหลังจาก backtest เสร็จทุกครั้ง เพื่อไม่ต้องรันใหม่

Usage:
  python save_results.py BTCUSDT DOGEUSDT BNBUSDT ETHUSDT
"""

import sys, os, json
from datetime import datetime
from backtest.runner import run_backtest, load_config

def save_one(symbol, cfg, results_dir="results"):
    """รัน backtest 1 เหรียญ แล้วบันทึกผลลัพธ์"""
    r = run_backtest(symbol, cfg)
    stats = r['stats']
    trades = r['trades']

    # ข้อมูลที่ต้องเก็บ
    result = {
        "symbol": symbol,
        "run_at": datetime.now().isoformat(),
        "config_hash": hash(json.dumps(cfg, sort_keys=True, default=str)),
        "stats": {
            "total_pnl_usd": float(round(stats['total_pnl_usd'], 2)),
            "max_drawdown_pct": float(round(stats['max_drawdown_pct'], 2)),
            "win_rate": float(round(stats['win_rate'], 1)),
            "total_trades": int(len(trades)),
            "total_volume_usd": float(round((trades['dca_count'] + 1).sum() * 200, 2)),  # 200 = size/trade
        },
        "trades_summary": {
            "max_dca_count": int(trades['dca_count'].max()),
            "avg_dca_count": float(round(trades['dca_count'].mean(), 2)),
            "median_dca_count": int(trades['dca_count'].median()),
            "max_holding_minutes": int(trades['holding_minutes'].max()),
            "avg_holding_minutes": float(round(trades['holding_minutes'].mean(), 1)),
            "liquidations": int((trades['close_reason'] == 'LIQUIDATE').sum()),
            "tp_count": int((trades['close_reason'] == 'TP').sum()),
            "end_count": int((trades['close_reason'] == 'END').sum()),
        },
        "margin_analysis": {
            "max_margin_used_usd": float(round((int(trades['dca_count'].max()) + 1) * 200 / 10, 2)),
            "free_margin_remaining": float(round(50000 - (int(trades['dca_count'].max()) + 1) * 200 / 10, 2)),
        },
        "side_breakdown": {
            "long": {
                "count": int((trades['side'] == 'LONG').sum()),
                "pnl": float(round(float(trades[trades['side'] == 'LONG']['pnl_usd'].sum()), 2)) if len(trades[trades['side'] == 'LONG']) > 0 else 0.0,
                "max_dca": int(trades[trades['side'] == 'LONG']['dca_count'].max()) if len(trades[trades['side'] == 'LONG']) > 0 else 0,
            },
            "short": {
                "count": int((trades['side'] == 'SHORT').sum()),
                "pnl": float(round(float(trades[trades['side'] == 'SHORT']['pnl_usd'].sum()), 2)) if len(trades[trades['side'] == 'SHORT']) > 0 else 0.0,
                "max_dca": int(trades[trades['side'] == 'SHORT']['dca_count'].max()) if len(trades[trades['side'] == 'SHORT']) > 0 else 0,
            },
        },
    }

    os.makedirs(results_dir, exist_ok=True)

    # บันทึก JSON รายเหรียญ
    json_path = os.path.join(results_dir, f"{symbol}_stats.json")
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # บันทึก trades เป็น CSV (เฉพาะคอลัมน์ที่จำเป็น)
    csv_path = os.path.join(results_dir, f"{symbol}_trades.csv")
    export_cols = ['symbol', 'side', 'open_time', 'close_time', 'ep', 'bep', 'tp', 
                   'dca_count', 'pnl_usd', 'pnl_pct', 'fee_usd', 'holding_minutes', 'close_reason']
    trades[export_cols].to_csv(csv_path, index=False)

    return result

def save_all(symbols, cfg=None):
    """รัน Backtest ทุกเหรียญ แล้วรวมเป็น summary"""
    if cfg is None:
        cfg = load_config()

    results = []
    for sym in symbols:
        r = save_one(sym, cfg)
        results.append(r)
        pnl = r['stats']['total_pnl_usd']
        dd = r['stats']['max_drawdown_pct']
        liq = r['trades_summary']['liquidations']
        max_dca = r['trades_summary']['max_dca_count']
        trades = r['stats']['total_trades']
        print(f"{sym}: PnL ${pnl:>8,.2f} | DD {dd:.2f}% | Max DCA {max_dca} | Liq {liq} | Trades {trades}")

    # สรุปรวม
    total_pnl = sum(r['stats']['total_pnl_usd'] for r in results)
    max_dd = max(r['stats']['max_drawdown_pct'] for r in results)
    total_trades = sum(r['stats']['total_trades'] for r in results)
    total_liq = sum(r['trades_summary']['liquidations'] for r in results)
    max_dca_all = max(r['trades_summary']['max_dca_count'] for r in results)

    summary = {
        "run_at": datetime.now().isoformat(),
        "symbols": symbols,
        "total_pnl_usd": round(total_pnl, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "total_trades": total_trades,
        "total_liquidations": total_liq,
        "max_dca_any_symbol": max_dca_all,
        "per_symbol": results,
    }

    summary_path = os.path.join("results", "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"TOTAL: PnL ${total_pnl:>10,.2f} | Max DD {max_dd:.2f}% | Trades {total_trades} | Liq {total_liq}")
    print(f"Results saved to: results/")
    print(f"  - summary.json (all stats)")
    for r in results:
        print(f"  - {r['symbol']}_stats.json + {r['symbol']}_trades.csv")

    return summary

if __name__ == "__main__":
    symbols = sys.argv[1:] if len(sys.argv) > 1 else ["BTCUSDT", "DOGEUSDT", "BNBUSDT", "ETHUSDT"]
    save_all(symbols)
