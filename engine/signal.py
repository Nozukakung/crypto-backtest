"""
engine/signal.py — Eye Tacle Original Signal (100% matched to commit 32b312c)
"""
import pandas as pd
from engine.indicators import compute_rsi, compute_candle_features
from engine.pattern_detector import detect_all_patterns

def detect_signals(df: pd.DataFrame, config: dict = None):
    if config is None:
        config = {}
        
    rsi_period = config.get("rsi_period", 14)
    rsi_long = config.get("rsi_long_threshold", 40.0)
    rsi_short = config.get("rsi_short_threshold", 60.0)
    
    # คำนวณ RSI + Candle features + Patterns
    df["rsi"] = compute_rsi(df["close"].values, rsi_period)
    df = compute_candle_features(df)
    df = detect_all_patterns(df)
    
    # เพิ่ม touch_pattern_3_low ถ้ายังไม่มี
    if "touch_pattern_3_low" not in df.columns:
        df["touch_pattern_3_low"] = df["touch_pattern_3"]  # fallback
    
    # สัญญาณขา LONG/SHORT (ตาเล็กเดิม)
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
    
    return df

def signal_summary(df):
    long_count = int(df["signal_long"].sum())
    short_count = int(df["signal_short"].sum())
    total = len(df)
    print(f"\n📊 Eye Tacle Signal Summary:")
    print(f"   Total candles: {total:,}")
    print(f"   Long signals:  {long_count:,} ({long_count/total*100:.2f}%)")
    print(f"   Short signals: {short_count:,} ({short_count/total*100:.2f}%)")