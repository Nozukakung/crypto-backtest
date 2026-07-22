#!/usr/bin/env python3
"""
stats.py — สถิติรายวัน/สัปดาห์/เดือน จาก Backtest
"""
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backtest.runner import run_backtest, load_config


def compute_periodic_stats(trades_df, size_per_trade_usd=200.0):
    """คำนวณสถิติรายวัน/สัปดาห์/เดือน จาก trades DataFrame"""
    df = trades_df.copy()
    df["close_time"] = pd.to_datetime(df["close_time"])
    df["date"] = df["close_time"].dt.date
    df["week"] = df["close_time"].dt.isocalendar().week.astype(int)
    df["month"] = df["close_time"].dt.to_period("M")

    # volume_usd = (dca_count + 1) * size_per_trade_usd * 2 (ขาซื้อ + ขาขาย)
    df["volume_usd"] = (df["dca_count"] + 1) * size_per_trade_usd * 2

    result = {}

    # ===== รายวัน =====
    daily = df.groupby("date").agg(
        trades=("pnl_usd", "count"),
        pnl=("pnl_usd", "sum"),
        avg_pnl=("pnl_usd", "mean"),
        volume_usd=("volume_usd", "sum"),
    ).reset_index()
    daily["cum_pnl"] = daily["pnl"].cumsum()
    result["daily"] = daily

    # ===== รายสัปดาห์ =====
    weekly = df.groupby("week").agg(
        trades=("pnl_usd", "count"),
        pnl=("pnl_usd", "sum"),
        avg_pnl=("pnl_usd", "mean"),
        volume_usd=("volume_usd", "sum"),
    ).reset_index()
    weekly["cum_pnl"] = weekly["pnl"].cumsum()
    result["weekly"] = weekly

    # ===== รายเดือน =====
    monthly = df.groupby("month").agg(
        trades=("pnl_usd", "count"),
        pnl=("pnl_usd", "sum"),
        avg_pnl=("pnl_usd", "mean"),
        volume_usd=("volume_usd", "sum"),
    ).reset_index()
    monthly["month"] = monthly["month"].astype(str)
    monthly["cum_pnl"] = monthly["pnl"].cumsum()
    result["monthly"] = monthly

    return result


if __name__ == "__main__":
    cfg = load_config()
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"

    print(f"🔄 Running backtest for {symbol}...")
    r = run_backtest(symbol, cfg)
    trades_df = r["trades"]

    print(f"\n{'='*60}")
    print(f"  📊 สถิติ {symbol}")
    print(f"{'='*60}")

    size_per_trade = cfg.get("strategy", {}).get("size_per_trade_usd", 200.0)
    stats = compute_periodic_stats(trades_df, size_per_trade)

    # ===== รายวัน =====
    daily = stats["daily"]
    print(f"\n📅 รายวัน (ทั้งหมด {len(daily)} วัน)")
    print(f"{'วัน':<12} | {'เทรด':>6} | {'PnL ($)':>10} | {'Volume ($)':>12} | {'Cum PnL ($)':>12}")
    print("-" * 65)
    for _, row in daily.head(10).iterrows():
        print(f"{str(row['date']):<12} | {int(row['trades']):>6} | {row['pnl']:>10,.2f} | {row['volume_usd']:>12,.0f} | {row['cum_pnl']:>12,.2f}")
    print(f"{'...':<12} | {'...':>6} | {'...':>10} | {'...':>12} | {'...':>12}")
    for _, row in daily.tail(5).iterrows():
        print(f"{str(row['date']):<12} | {int(row['trades']):>6} | {row['pnl']:>10,.2f} | {row['volume_usd']:>12,.0f} | {row['cum_pnl']:>12,.2f}")
    print(f"\n   เฉลี่ย/วัน: เทรด {daily['trades'].mean():.0f} ครั้ง | PnL ${daily['pnl'].mean():,.2f} | Volume ${daily['volume_usd'].mean():,.0f}")

    # ===== รายสัปดาห์ =====
    weekly = stats["weekly"]
    print(f"\n📆 รายสัปดาห์ (ทั้งหมด {len(weekly)} สัปดาห์)")
    print(f"{'สัปดาห์':<10} | {'เทรด':>6} | {'PnL ($)':>10} | {'Volume ($)':>12} | {'Cum PnL ($)':>12}")
    print("-" * 65)
    for _, row in weekly.iterrows():
        print(f"W{int(row['week']):<9} | {int(row['trades']):>6} | {row['pnl']:>10,.2f} | {row['volume_usd']:>12,.0f} | {row['cum_pnl']:>12,.2f}")
    print(f"\n   เฉลี่ย/สัปดาห์: เทรด {weekly['trades'].mean():.0f} ครั้ง | PnL ${weekly['pnl'].mean():,.2f} | Volume ${weekly['volume_usd'].mean():,.0f}")

    # ===== รายเดือน =====
    monthly = stats["monthly"]
    print(f"\n📊 รายเดือน (ทั้งหมด {len(monthly)} เดือน)")
    print(f"{'เดือน':<10} | {'เทรด':>6} | {'PnL ($)':>10} | {'Volume ($)':>12} | {'Cum PnL ($)':>12}")
    print("-" * 65)
    for _, row in monthly.iterrows():
        print(f"{row['month']:<10} | {int(row['trades']):>6} | {row['pnl']:>10,.2f} | {row['volume_usd']:>12,.0f} | {row['cum_pnl']:>12,.2f}")
    print(f"\n   เฉลี่ย/เดือน: เทรด {monthly['trades'].mean():.0f} ครั้ง | PnL ${monthly['pnl'].mean():,.2f} | Volume ${monthly['volume_usd'].mean():,.0f}")

    # ===== Summary =====
    total_days = len(daily)
    total_volume = daily["volume_usd"].sum()
    print(f"\n{'='*60}")
    print(f"  📈 สรุปรวม ({total_days} วัน)")
    print(f"{'='*60}")
    print(f"   จำนวนเทรดรวม: {len(trades_df):,} ครั้ง")
    print(f"   Volume รวม:    ${total_volume:,.0f}")
    print(f"   เทรดเฉลี่ย/วัน: {len(trades_df)/total_days:.0f} ครั้ง")
    print(f"   Volume เฉลี่ย/วัน: ${total_volume/total_days:,.0f}")
    print(f"   Volume เฉลี่ย/เดือน: ${total_volume/(total_days/30):,.0f}")
