"""
engine/pattern_detector.py — ตรวจจับ Candle Pattern ตามเงื่อนไขของกลยุทธ์
"""
import numpy as np
import pandas as pd


def detect_consecutive_high_closes(close: np.ndarray, high: np.ndarray,
                                    window: int = 5) -> np.ndarray:
    """
    ตรวจจับแท่งเขียวติดกัน >= window แท่ง (closes near high)
    return boolean array: True = มี pattern นี้ (ไม่ควรเปิด Long)

    ตามโพสต์: "ไม่มี pattern เชี่ยว → แตะ → แตะ (2-3 แท่ง) หรือ เชี่ยว 5 ตัว"
    เชี่ยว在这里 = แท่งที่ปิดสูง (close อยู่ใกล้ high)
    """
    n = len(close)
    result = np.zeros(n, dtype=bool)

    for i in range(window - 1, n):
        count = 0
        for j in range(window):
            idx = i - j
            if close[idx] >= high[idx] * 0.998:  # ปิดสูงมาก (99.8% ของ high)
                count += 1
            else:
                break
        if count >= window:
            result[i] = True

    return result


def detect_touch_pattern(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                          window: int = 3) -> np.ndarray:
    """
    ตรวจจับ Pattern "แตะ → แตะ → แตะ" (2-3 แท่ง)
    หมายถึง: แท่งติดกันมี high หรือ low ใกล้เคียงกัน (range แคบ)

    return boolean array: True = มี pattern นี้
    """
    n = len(close)
    result = np.zeros(n, dtype=bool)

    for i in range(window - 1, n):
        # ดึงแท่งย้อนหลัง window แท่ง
        highs = high[i - window + 1: i + 1]
        lows = low[i - window + 1: i + 1]
        ranges = highs - lows

        # ถ้าทุกแท่งมี range แคบ (น้อยกว่า 0.1% ของราคา)
        avg_price = np.mean(close[i - window + 1: i + 1])
        if avg_price > 0 and np.all(ranges < avg_price * 0.001):
            result[i] = True

    return result


def detect_consecutive_low_closes(close: np.ndarray, low: np.ndarray,
                                    window: int = 5) -> np.ndarray:
    """
    ตรวจจับแท่งแดงติดกัน >= window แท่ง (closes near low)
    return boolean array: True = มี pattern นี้ (ไม่ควรเปิด Short)

    สำหรับ Short signal: "ไม่มี pattern แตะ → เชี่ยว → เชี่ยว"
    """
    n = len(close)
    result = np.zeros(n, dtype=bool)

    for i in range(window - 1, n):
        count = 0
        for j in range(window):
            idx = i - j
            if close[idx] <= low[idx] * 1.002:  # ปิดต่ำมาก (อยู่ใน 0.2% ของ low)
                count += 1
            else:
                break
        if count >= window:
            result[i] = True

    return result


def detect_all_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """ตรวจจับ pattern ทั้งหมดและเพิ่มเป็นคอลัมน์"""
    df = df.copy()

    h, l, c = df["high"].values, df["low"].values, df["close"].values

    # สำหรับ Long: เช็คว่าไม่มี consecutive high closes
    df["consec_high_5"] = detect_consecutive_high_closes(c, h, window=5)

    # สำหรับ Long: เช็คว่าไม่มี touch pattern (3 แท่ง)
    df["touch_pattern_3"] = detect_touch_pattern(h, l, c, window=3)

    # สำหรับ Short: เช็คว่าไม่มี consecutive low closes
    df["consec_low_5"] = detect_consecutive_low_closes(c, l, window=5)

    # แท่งล่าสุดไม่ปิดที่ Low (Long condition)
    from engine.indicators import compute_candle_features
    df = compute_candle_features(df)

    return df