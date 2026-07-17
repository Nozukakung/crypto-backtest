"""
engine/signal.py — ตรวจจับสัญญาณ Long/Short จาก RSI + Candle Pattern
"""
import numpy as np
import pandas as pd
from engine.indicators import compute_rsi, compute_candle_features
from engine.pattern_detector import detect_all_patterns


def detect_signals(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    ตรวจจับสัญญาณ Long/Short ตามเงื่อนไขกลยุทธ์

    Long:
    - RSI(14) < rsi_long_threshold (default 40)
    - แท่งล่าสุดไม่ปิดที่ Low
    - ไม่มี Pattern เชี่ยว 5 ตัวติด
    - ไม่มี Pattern แตะ→แตะ→แตะ

    Short:
    - RSI(14) > rsi_short_threshold (default 60)
    - ไม่มี Pattern แดงติดกัน 5 ตัว
    - ไม่มี touch pattern
    """
    df = compute_rsi(df)
    df = compute_candle_features(df)
    df = detect_all_patterns(df)

    rsi_long = config.get("rsi_long_threshold", 40)
    rsi_short = config.get("rsi_short_threshold", 60)

    df["signal_long"] = False
    df["signal_short"] = False

    # --- Long Signal ---
    long_cond = (
        (df["rsi"] < rsi_long) &
        (~df["closes_at_low"]) &
        (~df["consec_high_5"]) &
        (~df["touch_pattern_3"])
    )
    df.loc[long_cond, "signal_long"] = True

    # --- Short Signal ---
    short_cond = (
        (df["rsi"] > rsi_short) &
        (~df["consec_low_5"]) &
        (~df["touch_pattern_3"])
    )
    df.loc[short_cond, "signal_short"] = True

    return df


def signal_summary(df: pd.DataFrame) -> dict:
    """สรุปสถิติ signal"""
    total = len(df)
    long_signals = df["signal_long"].sum()
    short_signals = df["signal_short"].sum()

    print(f"📊 Signal Summary:")
    print(f"   Total candles: {total:,}")
    print(f"   Long signals:  {long_signals:,} ({long_signals/total*100:.2f}%)")
    print(f"   Short signals: {short_signals:,} ({short_signals/total*100:.2f}%)")
    print(f"   No signal:     {total - long_signals - short_signals:,} ({(total-long_signals-short_signals)/total*100:.2f}%)")

    return {
        "total": total,
        "long": int(long_signals),
        "short": int(short_signals),
        "none": int(total - long_signals - short_signals),
        "long_pct": float(long_signals / total * 100),
        "short_pct": float(short_signals / total * 100),
    }