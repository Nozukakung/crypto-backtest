#!/usr/bin/env python3
"""
query_results.py — วิเคราะห์ผลลัพธ์ Backtest จากที่บันทึกไว้
ไม่ต้องรัน Backtest ใหม่!

Usage:
  python query_results.py                # สรุปทั้งหมด
  python query_results.py BTCUSDT        # สรุปเหรียญเดียว
  python query_results.py --compare      # เทียบกับ saved config ต่างๆ
"""

import sys, os, json
import glob
from datetime import datetime

RESULTS_DIR = "results/latest"

def load_results():
    """โหลด summary.json และไฟล์ stats ทั้งหมด"""
    summary_path = os.path.join(RESULTS_DIR, "summary.json")
    if not os.path.exists(summary_path):
        # ถ้าไม่มี summary.json ลองหา in folder
        stats_files = sorted(glob.glob(os.path.join(RESULTS_DIR, "*_stats.json")))
        # กรอง _last_run.txt ออก
        stats_files = [f for f in stats_files if not os.path.basename(f).startswith("_")]
        if not stats_files:
            return None
        results = []
        for f in stats_files:
            with open(f) as fp:
                results.append(json.load(fp))
        # build summary
        total_pnl = sum(r['stats']['total_pnl_usd'] for r in results)
        max_dd = max(r['stats']['max_drawdown_pct'] for r in results)
        total_trades = sum(r['stats']['total_trades'] for r in results)
        total_liq = sum(r['trades_summary']['liquidations'] for r in results)
        return {
            "run_at": results[0]['run_at'] if results else "unknown",
            "symbols": [r['symbol'] for r in results],
            "total_pnl_usd": total_pnl,
            "max_drawdown_pct": max_dd,
            "total_trades": total_trades,
            "total_liquidations": total_liq,
            "per_symbol": results,
        }

    with open(summary_path) as f:
        return json.load(f)


def symbol_trades(symbol):
    """โหลด CSV trades ของเหรียญที่ระบุ"""
    path = os.path.join(RESULTS_DIR, f"{symbol}_trades.csv")
    if not os.path.exists(path):
        return None
    import pandas as pd
    return pd.read_csv(path)


def show_summary(data):
    """แสดงตารางสรุป"""
    if data is None:
        print("❌ ไม่พบผลลัพธ์ที่บันทึกไว้ กรุณารัน `python save_results.py` ก่อน")
        return

    print(f"\n{'='*70}")
    print(f"📊 Summary (Saved: {data.get('run_at', 'unknown')})")
    print(f"{'='*70}")
    print(f"| {'Symbol':<8} | {'PnL':>12} | {'DD':>6} | {'Max DCA':>7} | {'Liq':>4} | {'Trades':>7} | {'WR':>6} |")
    print(f"|{'-'*8}-|-{'-'*12}-|-{'-'*6}-|-{'-'*7}-|-{'-'*4}-|-{'-'*7}-|-{'-'*6}|")

    for r in data.get('per_symbol', []):
        s = r['stats']
        ts = r['trades_summary']
        side = r.get('side_breakdown', {})
        print(f"| {r['symbol']:<8} | ${s['total_pnl_usd']:>9,.2f} | {s['max_drawdown_pct']:>5.2f}% | {ts['max_dca_count']:>7} | {ts['liquidations']:>4} | {s['total_trades']:>7} | {s['win_rate']:>5.1f}% |")

    print(f"|{'-'*8}-|-{'-'*12}-|-{'-'*6}-|-{'-'*7}-|-{'-'*4}-|-{'-'*7}-|-{'-'*6}|")
    print(f"| {'TOTAL':<8} | ${data['total_pnl_usd']:>9,.2f} | {data['max_drawdown_pct']:>5.2f}% | {data.get('max_dca_any_symbol', '-'):>7} | {data['total_liquidations']:>4} | {data['total_trades']:>7} | {'-':>5} |")
    print()


def show_symbol_detail(symbol):
    """แสดงรายละเอียดเหรียญเดียว"""
    data = load_results()
    if data is None:
        print("❌ ไม่พบผลลัพธ์")
        return

    for r in data.get('per_symbol', []):
        if r['symbol'] == symbol:
            print(f"\n{'='*60}")
            print(f"🔍 {symbol}")
            print(f"{'='*60}")
            s = r['stats']
            ts = r['trades_summary']
            ma = r.get('margin_analysis', {})
            side = r.get('side_breakdown', {})

            print(f"  พื้นฐาน:")
            print(f"    PnL:          ${s['total_pnl_usd']:>10,.2f}")
            print(f"    Drawdown:     {s['max_drawdown_pct']:.2f}%")
            print(f"    Win Rate:     {s['win_rate']:.1f}%")
            print(f"    Volume:       ${s.get('total_volume_usd', 0):>10,.2f}")
            print(f"  DCA:")
            print(f"    Max DCA:      {ts['max_dca_count']} ไม้")
            print(f"    Avg DCA:      {ts['avg_dca_count']}")
            print(f"    Median DCA:   {ts['median_dca_count']}")
            print(f"    Margin สูงสุด: ${ma.get('max_margin_used_usd', 0):,.0f}")
            print(f"    Free Margin:  ${ma.get('free_margin_remaining', 0):,.0f}")
            print(f"  การถือครอง:")
            print(f"    Avg Hold:     {ts['avg_holding_minutes']:.0f} นาที ({ts['avg_holding_minutes']/1440:.1f} วัน)")
            print(f"    Max Hold:     {ts['max_holding_minutes']} นาที ({ts['max_holding_minutes']/1440:.1f} วัน)")
            print(f"  สาเหตุปิด:")
            print(f"    TP:           {ts['tp_count']}")
            print(f"    END:          {ts['end_count']}")
            print(f"    LIQUIDATE:    {ts['liquidations']} ครั้ง")
            print(f"  แยกฝั่ง:")
            print(f"    LONG:         {side.get('long', {}).get('count', '-')} trades | PnL ${side.get('long', {}).get('pnl', 0):>8,.2f} | Max DCA {side.get('long', {}).get('max_dca', '-')}")
            print(f"    SHORT:        {side.get('short', {}).get('count', '-')} trades | PnL ${side.get('short', {}).get('pnl', 0):>8,.2f} | Max DCA {side.get('short', {}).get('max_dca', '-')}")
            return

    print(f"❌ ไม่พบ {symbol} ในผลลัพธ์")


def top_dca_trades(symbol, n=5):
    """แสดง trade ที่ DCA มากที่สุดของเหรียญ"""
    df = symbol_trades(symbol)
    if df is None:
        print(f"❌ ไม่พบ trades CSV สำหรับ {symbol}")
        return

    top = df.nlargest(n, 'dca_count')
    print(f"\n🏆 Top {n} Trades (Max DCA) ของ {symbol}")
    print(f"{'DCA':>6} | {'Side':<6} | {'EP':>10} | {'BEP':>10} | {'PnL':>8} | {'Hold(min)':>9} | {'Reason'}")
    print(f"{'-'*6}-|-{'-'*6}-|-{'-'*10}-|-{'-'*10}-|-{'-'*8}-|-{'-'*9}-|-{'-'*8}")
    for _, t in top.iterrows():
        print(f"{int(t['dca_count']):>6} | {t['side']:<6} | ${t['ep']:>8,.2f} | ${t['bep']:>8,.2f} | ${t['pnl_usd']:>6,.2f} | {int(t['holding_minutes']):>9} | {t['close_reason']}")


def compare_configs():
    """เทียบกับ results ที่บันทึกไว้ในโฟลเดอร์อื่น (config เก่า)"""
    # ตรวจสอบ results/configs/ (ถ้ามี sub-folders)
    configs_dir = os.path.join(RESULTS_DIR, "configs")
    if not os.path.isdir(configs_dir):
        print("ℹ️  ไม่พบโฟลเดอร์ results/configs/ ให้เปรียบเทียบ")
        print("   วิธีใช้: python save_results.py → เก็บ result ปัจจุบัน")
        print("   เปลี่ยน Config → python save_results.py → เก็บผล config ใหม่")
        print("   ใช้ --compare เปรียบเทียบทั้งสอง config")
        return

    # หาโฟลเดอร์ย่อยทั้งหมด
    configs = sorted(os.listdir(configs_dir))
    if not configs:
        print("ℹ️  ไม่มี config เก่าให้เปรียบเทียบ")
        return

    for cfg_name in configs:
        cfg_path = os.path.join(configs_dir, cfg_name, "summary.json")
        if not os.path.exists(cfg_path):
            continue
        with open(cfg_path) as f:
            data = json.load(f)
        print(f"\n📁 Config: {cfg_name}")
        show_summary(data)


if __name__ == "__main__":
    if "--compare" in sys.argv:
        compare_configs()
        sys.exit(0)

    # หาว่าต้องการดูเหรียญไหน
    symbols = [a for a in sys.argv[1:] if not a.startswith("--")]

    if len(symbols) == 0:
        # แสดงสรุปทั้งหมด
        data = load_results()
        show_summary(data)
    elif len(symbols) == 1:
        show_symbol_detail(symbols[0])
    else:
        # แสดงรวม
        data = load_results()
        show_summary(data)
        for sym in symbols:
            show_symbol_detail(sym)
