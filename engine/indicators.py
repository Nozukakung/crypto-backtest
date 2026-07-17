"""
engine/indicators.py — คำนวณ Technical Indicators แบบ NumPy vectorized
"""
import numpy as np


def compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """
    คำนวณ RSI (Wilder's RSI) แบบ Vectorized
    ใช้ pandas EWM แทน loop เพื่อความเร็ว
    """
    import pandas as pd

    close_series = pd.Series(close)
    delta = close_series.diff()

    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # Wilder's smoothing (EMA with alpha = 1/period)
    avg_gain = gain.ewm(alpha=1.0/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi.values


def compute_candle_features(df):
    """
    คำนวณฟีเจอร์ของแท่งเทียนที่ต้องใช้ใน pattern detection
    """
    import pandas as pd

    df = df.copy()
    df["prev_close"] = df["close"].shift(1)
    df["prev_low"] = df["low"].shift(1)
    df["prev_high"] = df["high"].shift(1)

    # ปิดที่ Low?
    df["closes_at_low"] = (df["close"] <= df["low"] * 1.0001)  # ใกล้ low

    # ปิดที่ High?
    df["closes_at_high"] = (df["close"] >= df["high"] * 0.9999)

    # Body size
    df["body_size"] = (df["close"] - df["open"]).abs()
    df["range_size"] = df["high"] - df["low"]
    df["body_ratio"] = df["body_size"] / df["range_size"].replace(0, np.nan)

    # วิ่งขึ้น/ลง
    df["is_green"] = df["close"] > df["open"]
    df["is_red"] = df["close"] < df["open"]

    return df


def detect_candle_patterns(df, window: int = 5):
    """
    ตรวจจับรูปแบบแท่งเทียนที่กลยุทธ์ต้องการ
    """
    import pandas as pd

    df = df.copy()

    # 1. Consecutive high closes (5 แท่งปิดสูงติดกัน) - สำหรับกรอง Long
    # เช็คว่าแท่งก่อนหน้า 5 แท่ง close >= open
    green_count = df["is_green"].rolling(window, min_periods=window).sum()
    df["consec_high_5"] = (green_count == window)

    # 2. Consecutive low closes (5 แท่งปิดต่ำติดกัน) - สำหรับกรอง Short
    red_count = df["is_red"].rolling(window, min_periods=window).sum()
    df["consec_low_5"] = (red_count == window)

    # 3. Touch pattern (แตะ → แตะ → แตะ) 2-3 แท่ง
    # ราคาแตะ high/low แล้วไม่ break
    # สำหรับ Long: เช็คว่าไม่มีรูปแบบที่ high ถูกแตะแล้วไม่ break
    # แพทเทิร์น: แท่งก่อนหน้า 2-3 แท่ง มี high ใกล้กัน
    # Simple heuristic: high ของ 3 แท่งก่อนไม่ต่างกันมาก
    df["high_3_close"] = df["high"].rolling(3, min_periods=3).apply(
        lambda x: np.max(x) - np.min(x), raw=True
    )
    # ถ้า high 3 แท่งอยู่ในช่วงแคบ (< 0.2%) = touch pattern
    df["touch_pattern_3"] = (df["high_3_close"] / df["close"] < 0.002)

    # 4. Pattern สำหรับ Short: low touch
    df["low_3_close"] = df["low"].rolling(3, min_periods=3).apply(
        lambda x: np.max(x) - np.min(x), raw=True
    )
    df["touch_pattern_3_low"] = (df["low_3_close"] / df["close"] < 0.002)

    return df


def detect_all_patterns(df):
    """รวม pattern detection ทั้งหมด"""
    df = compute_candle_features(df)
    df = detect_candle_patterns(df)
    return df