"""
engine/indicators.py — คำนวณ Technical Indicators (RSI + Candle Patterns)
v2: เพิ่ม Pattern Detection ซับซ้อนขึ้นตามโพสต์ตาเล็ก

ตาเล็ก: "เขียนให้บอทเช็คได้ว่า ณ แท่งนี้ มันคือ **แพทเทิร์นอะไรตามตำรา**"
Patterns ที่ตรวจจับ:
1. Consecutive high closes (แท่งเขียวติดกัน 5+) — สำหรับกรอง Long
2. Consecutive low closes (แท่งแดงติดกัน 5+) — สำหรับกรอง Short
3. Touch pattern "แตะ→แตะ→แตะ" (3 แท่ง) — range แคบ
4. Wick rejection (หางยาว = การปฏิเสธราคา)
5. Inside bar (แท่งถัดมาอยู่ภายในแท่งก่อน)
6. Pin bar (แท่งหางยาว = สัญญาณกลับตัว)
"""
import numpy as np
import pandas as pd


def compute_ema(close, period):
    """EMA แบบ Wilder (pandas ewm)"""
    return pd.Series(close).ewm(span=period, adjust=False).mean().values


def compute_bollinger_bands(close, period=20, num_std=2.0):
    """Bollinger Bands: Upper, Middle (SMA), Lower"""
    close_series = pd.Series(close)
    middle = close_series.rolling(period).mean()
    std = close_series.rolling(period).std()
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    return upper.values, middle.values, lower.values


def compute_adx(high, low, close, period=14):
    """ADX (Average Directional Index) วัดความแรงของเทรนด์"""
    high_series = pd.Series(high)
    low_series = pd.Series(low)
    close_series = pd.Series(close)

    # True Range
    tr1 = high_series - low_series
    tr2 = (high_series - close_series.shift(1)).abs()
    tr3 = (low_series - close_series.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    up_move = high_series - high_series.shift(1)
    down_move = low_series.shift(1) - low_series

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high_series.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high_series.index)

    # Smoothed averages (Wilder's)
    atr = tr.ewm(alpha=1.0/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1.0/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1.0/period, adjust=False).mean() / atr)

    # DX and ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1.0/period, adjust=False).mean()

    return adx.values, plus_di.values, minus_di.values


def compute_rsi(close, period=14):
    """RSI แบบ Wilder's"""
    close_series = pd.Series(close)
    delta = close_series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.values


def compute_candle_features(df):
    """คำนวณฟีเจอร์แท่งเทียน"""
    df = df.copy()
    df["prev_close"] = df["close"].shift(1)
    df["prev_low"] = df["low"].shift(1)
    df["prev_high"] = df["high"].shift(1)
    df["prev_open"] = df["open"].shift(1)

    df["closes_at_low"] = (df["close"] <= df["low"] * 1.0001)
    df["closes_at_high"] = (df["close"] >= df["high"] * 0.9999)

    df["body_size"] = (df["close"] - df["open"]).abs()
    df["range_size"] = df["high"] - df["low"]
    df["body_ratio"] = df["body_size"] / df["range_size"].replace(0, np.nan)

    df["is_green"] = df["close"] > df["open"]
    df["is_red"] = df["close"] < df["open"]
    return df


def detect_candle_patterns(df, window=5):
    """
    ตรวจจับ Pattern ซับซ้อน (ตามโพสต์ตาเล็กที่บอกว่าเป็น "ไม้ตาย")
    """
    df = df.copy()

    # --- Pattern 1: Consecutive high closes (5+ แท่ง) ---
    green_count = df["is_green"].rolling(window, min_periods=window).sum()
    df["consec_high_5"] = (green_count == window)

    # --- Pattern 2: Consecutive low closes (5+ แท่ง) ---
    red_count = df["is_red"].rolling(window, min_periods=window).sum()
    df["consec_low_5"] = (red_count == window)

    # --- Pattern 3: Touch pattern (range แคบ 3 แท่ง) ---
    df["high_3_spread"] = df["high"].rolling(3, min_periods=3).apply(
        lambda x: np.max(x) - np.min(x), raw=True
    )
    df["touch_pattern_3"] = (df["high_3_spread"] / df["close"] < 0.002)

    df["low_3_spread"] = df["low"].rolling(3, min_periods=3).apply(
        lambda x: np.max(x) - np.min(x), raw=True
    )
    df["touch_pattern_3_low"] = (df["low_3_spread"] / df["close"] < 0.002)

    # --- Pattern 4: Wick rejection ---
    # หางล่างยาว (Long lower wick) = การปฏิเสธราคาต่ำ → สำหรับ Long
    df["lower_wick_ratio"] = (pd.concat([df["open"], df["close"]], axis=1).min(axis=1) - df["low"]) / df["range_size"].replace(0, np.nan)
    df["long_lower_wick"] = df["lower_wick_ratio"] > 0.6  # หางล่างยาว > 60% ของ range

    # หางบนยาว (Long upper wick) = การปฏิเสธราคาสูง → สำหรับ Short
    df["upper_wick_ratio"] = (df["high"] - pd.concat([df["open"], df["close"]], axis=1).max(axis=1)) / df["range_size"].replace(0, np.nan)
    df["long_upper_wick"] = df["upper_wick_ratio"] > 0.6

    # --- Pattern 5: Inside bar ---
    # แท่งถัดมา range อยู่ภายในแท่งก่อนหน้า
    df["inside_bar"] = (df["high"] <= df["prev_high"]) & (df["low"] >= df["prev_low"])

    # --- Pattern 6: Pin bar ---
    # แท่งหางยาว + body เล็ก = สัญญาณกลับตัว
    df["pin_bar_bull"] = df["long_lower_wick"] & (df["body_ratio"] < 0.3)
    df["pin_bar_bear"] = df["long_upper_wick"] & (df["body_ratio"] < 0.3)

    return df


def detect_all_patterns(df):
    """รวม pattern detection"""
    df = compute_candle_features(df)
    df = detect_candle_patterns(df)
    return df


def compute_ibs(high, low, close):
    """IBS (Internal Bar Strength) = (Close - Low) / (High - Low)
    ค่า 0-1, ต่ำ = ปิดใกล้ Low = Exhaustion selling"""
    h = pd.Series(high)
    l = pd.Series(low)
    c = pd.Series(close)
    rng = (h - l).replace(0, np.nan)
    return ((c - l) / rng).values


def compute_volume_spike(volume, period=20, multiplier=2.0):
    """Volume Spike: Volume > multiplier × เฉลี่ย period แท่งที่ผ่านมา"""
    vol = pd.Series(volume)
    avg_vol = vol.rolling(period, min_periods=period).mean()
    return (vol > avg_vol * multiplier).values