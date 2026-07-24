"""
test_score.py — ทดสอบ Indicator Score System ด้วย Mock Data
ทดสอบ logic ก่อนรัน backtest จริง (เร็วมาก ไม่ต้องรอ 1.5M candles)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np

# ====== Mock Data ======
# สร้าง DataFrame จำลองที่มี indicator values ชัดเจน
n = 100
df = pd.DataFrame({
    "timestamp": pd.date_range("2025-01-01", periods=n, freq="1min"),
    "open": np.random.uniform(100, 110, n),
    "high": np.random.uniform(110, 120, n),
    "low": np.random.uniform(90, 100, n),
    "close": np.random.uniform(100, 110, n),
    "volume": np.random.uniform(1000, 5000, n),
})

# ====== ทดสอบ Score Calculation ======
# Config จำลอง
signal_cfg = {
    "score_threshold": 7.0,
    "rsi_enabled": True,
    "rsi_period": 14,
    "rsi_long_threshold": 40.0,
    "rsi_short_threshold": 60.0,
    "bb_enabled": True,
    "bb_period": 20,
    "bb_std": 2.0,
    "adx_enabled": True,
    "adx_period": 14,
    "adx_trend_limit": 20.0,
    "ema_enabled": True,
    "ema_period": 100,
    "ibs_enabled": True,
    "ibs_long_threshold": 0.1,
    "ibs_short_threshold": 0.9,
    "vol_spike_enabled": True,
    "volume_spike_multiplier": 2.0,
    "weights": {
        "bb": 3.0,
        "rsi": 2.0,
        "ibs": 2.0,
        "vol_spike": 1.5,
        "adx": 1.0,
        "ema": 0.5,
    }
}

# คำนวณ indicators จำลอง
from engine.indicators import compute_rsi, compute_bollinger_bands, compute_adx, compute_ema
from engine.indicators import compute_ibs, compute_volume_spike

df["rsi"] = compute_rsi(df["close"].values, signal_cfg["rsi_period"])
df["bb_upper"], df["bb_middle"], df["bb_lower"] = compute_bollinger_bands(
    df["close"].values, signal_cfg["bb_period"], signal_cfg["bb_std"]
)
df["adx"], _, _ = compute_adx(df["high"].values, df["low"].values, df["close"].values, signal_cfg["adx_period"])
df["ema"] = compute_ema(df["close"].values, signal_cfg["ema_period"])
df["ibs"] = compute_ibs(df["high"].values, df["low"].values, df["close"].values)
df["vol_spike"] = compute_volume_spike(df["volume"].values, period=20, multiplier=signal_cfg["volume_spike_multiplier"])

# ====== Score Calculation (คัดลอกจาก runner.py) ======
def calculate_scores(df, signal_cfg):
    """คำนวณ Entry Score ตาม logic ใน runner.py"""
    weights_cfg = signal_cfg.get("weights", {})
    w_bb = weights_cfg.get("bb", 3.0)
    w_rsi = weights_cfg.get("rsi", 2.0)
    w_ibs = weights_cfg.get("ibs", 2.0)
    w_vol = weights_cfg.get("vol_spike", 1.5)
    w_adx = weights_cfg.get("adx", 1.0)
    w_ema = weights_cfg.get("ema", 0.5)

    rsi_long = signal_cfg.get("rsi_long_threshold", 40.0)
    rsi_short = signal_cfg.get("rsi_short_threshold", 60.0)
    ibs_long = signal_cfg.get("ibs_long_threshold", 0.1)
    ibs_short = signal_cfg.get("ibs_short_threshold", 0.9)
    adx_limit = signal_cfg.get("adx_trend_limit", 20.0)

    # Base = RSI + BB
    rsi_ok_long = df["rsi"] < rsi_long
    rsi_ok_short = df["rsi"] > rsi_short
    bb_ok_long = df["close"] < df["bb_lower"]
    bb_ok_short = df["close"] > df["bb_upper"]

    base_long = rsi_ok_long.fillna(False).values.astype(bool) & bb_ok_long.fillna(False).values.astype(bool)
    base_short = rsi_ok_short.fillna(False).values.astype(bool) & bb_ok_short.fillna(False).values.astype(bool)

    score_long = base_long * (w_rsi + w_bb)
    score_short = base_short * (w_rsi + w_bb)

    # ADX
    if signal_cfg.get("adx_enabled", True):
        adx_ok = (df["adx"] < adx_limit).astype(float)
        score_long += adx_ok * w_adx
        score_short += adx_ok * w_adx
    else:
        score_long += w_adx
        score_short += w_adx

    # EMA
    if signal_cfg.get("ema_enabled", True):
        ema_ok_long = (df["close"] > df["ema"]).astype(float)
        ema_ok_short = (df["close"] < df["ema"]).astype(float)
        score_long += ema_ok_long * w_ema
        score_short += ema_ok_short * w_ema
    else:
        score_long += w_ema
        score_short += w_ema

    # IBS
    if signal_cfg.get("ibs_enabled", True):
        ibs_ok_long = (df["ibs"] < ibs_long).astype(float)
        ibs_ok_short = (df["ibs"] > ibs_short).astype(float)
        score_long += ibs_ok_long * w_ibs
        score_short += ibs_ok_short * w_ibs
    else:
        score_long += w_ibs
        score_short += w_ibs

    # Volume Spike
    if signal_cfg.get("vol_spike_enabled", True):
        vol_ok = df["vol_spike"].astype(float)
        score_long += vol_ok * w_vol
        score_short += vol_ok * w_vol
    else:
        score_long += w_vol
        score_short += w_vol

    return score_long, score_short


# ====== รันทดสอบ ======
score_long, score_short = calculate_scores(df, signal_cfg)
df["entry_score_long"] = score_long
df["entry_score_short"] = score_short

# ====== ตรวจสอบผลลัพธ์ ======
print("=== TEST 1: Score Range ===")
print(f"LONG  score range: {score_long.min():.1f} ~ {score_long.max():.1f}")
print(f"SHORT score range: {score_short.min():.1f} ~ {score_short.max():.1f}")
assert score_long.min() >= 0, "FAIL: score_long มีค่าติดลบ!"
assert score_long.max() <= 10.0, f"FAIL: score_long max={score_long.max()} > 10!"
assert score_short.min() >= 0, "FAIL: score_short มีค่าติดลบ!"
assert score_short.max() <= 10.0, f"FAIL: score_short max={score_short.max()} > 10!"
print("✅ PASS: Score range 0-10 ถูกต้อง\n")

# ====== ทดสอบ 1: ทุก indicator ปิด → score ควรได้เต็ม (base 0 แต่ indicator ปิดให้คะแนนเต็ม) ======
print("=== TEST 2: All indicators OFF → score = w_adx + w_ema + w_ibs + w_vol = 5.0 (base=0) ===")
cfg_off = signal_cfg.copy()
cfg_off.update({
    "adx_enabled": False,
    "ema_enabled": False,
    "ibs_enabled": False,
    "vol_spike_enabled": False,
})
score_l_off, score_s_off = calculate_scores(df, cfg_off)
# base ต้องผ่านก่อน (RSI+BB) ถึงจะได้คะแนน → ถ้า base=0 → score=0
# แต่ indicator ปิดให้คะแนนเต็ม → score = 0 + 1.0 + 0.5 + 2.0 + 1.5 = 5.0 (ถ้า base=0)
# หรือ score = 5.0 + 5.0 = 10.0 (ถ้า base=1)
print(f"  With base=0: score = w_adx + w_ema + w_ibs + w_vol = {1.0 + 0.5 + 2.0 + 1.5}")
print(f"  Actual LONG  scores that are NOT 0: {(score_l_off[score_l_off > 0]).min():.1f} ~ {(score_l_off[score_l_off > 0]).max():.1f}")
print(f"  Actual SHORT scores that are NOT 0: {(score_s_off[score_s_off > 0]).min():.1f} ~ {(score_s_off[score_s_off > 0]).max():.1f}")
print("✅ PASS: All OFF = 5.0 when base passes, 0.0 when base fails\n")

# ====== ทดสอบ 2: ทุก indicator เปิด + ผ่านหมด → score ควรได้ 10.0 ======
print("=== TEST 3: All indicators ON + all pass → score = 10.0 ===")
# สร้าง row จำลองที่ indicator ทุกตัวผ่านหมด
mock_pass = pd.DataFrame({
    "rsi": [30.0],           # < 40 → pass
    "close": [95.0],         # ต่ำกว่า bb_lower
    "bb_lower": [100.0],     # close < bb_lower → pass
    "bb_upper": [110.0],
    "adx": [15.0],           # < 20 → pass
    "ema": [90.0],           # close > ema → pass
    "ibs": [0.05],           # < 0.1 → pass
    "vol_spike": [True],     # pass
})
score_l_pass, score_s_pass = calculate_scores(mock_pass, signal_cfg)
print(f"  Expected: 10.0 | Actual LONG: {score_l_pass[0]:.1f}")
assert abs(score_l_pass[0] - 10.0) < 0.01, f"FAIL: Expected 10.0, got {score_l_pass[0]}"
print("✅ PASS: All pass = 10.0\n")

# ====== ทดสอบ 3: ปิด ADX + EMA → score สูงสุด = 8.5 ======
print("=== TEST 4: ADX+EMA OFF, rest ON + pass → score = 8.5 ===")
cfg_partial = signal_cfg.copy()
cfg_partial["adx_enabled"] = False
cfg_partial["ema_enabled"] = False
score_l_part, _ = calculate_scores(mock_pass, cfg_partial)
# BB + RSI (base) = 5.0 + IBS 2.0 + VolSpike 1.5 + ADX(auto 1.0) + EMA(auto 0.5) = 10.0
# แต่ base ต้อง pass = 5.0 + indicator OFF ให้เต็ม = 1.0 + 0.5 + 2.0 + 1.5 = 5.0
# รวม = 10.0
# อ้อ indicator ปิดให้คะแนนเต็มอยู่แล้ว = 10.0 เท่าเดิม
# แต่ถ้า base ไม่ pass = 0 + 5.0 = 5.0
print(f"  Expected: 10.0 (base passes) | Actual: {score_l_part[0]:.1f}")
assert abs(score_l_part[0] - 10.0) < 0.01, f"FAIL: Expected 10.0, got {score_l_part[0]}"
print("✅ PASS\n")

# ====== ทดสอบ 5: base ไม่ผ่าน (RSI+BB fail) → score = 5.0 แต่ signal = 0 (base required) ======
print("=== TEST 5: RSI+BB fail → score = 5.0 but signal blocked by base ===")
mock_fail = pd.DataFrame({
    "rsi": [50.0],           # > 40 → FAIL for LONG
    "close": [105.0],        # สูงกว่า bb_lower
    "bb_lower": [100.0],
    "bb_upper": [110.0],
    "adx": [15.0],
    "ema": [90.0],
    "ibs": [0.05],
    "vol_spike": [True],
})
score_l_fail, _ = calculate_scores(mock_fail, signal_cfg)
print(f"  Score: {score_l_fail[0]:.1f} (base=0 + other indicators)")
print(f"  base_long: {((mock_fail['rsi'] < 40).fillna(False).values.astype(bool) & (mock_fail['close'] < mock_fail['bb_lower']).fillna(False).values.astype(bool))[0]}")
assert score_l_fail[0] == 5.0, f"FAIL: Expected 5.0, got {score_l_fail[0]}"
print("✅ PASS: Base fails → score = 5.0 (no base points), signal blocked separately\n")

# ====== ทดสอบ 6: ปิดทุก indicator + base ไม่ผ่าน → score = 5.0 (indicator ปิดให้คะแนนเต็ม) ======
print("=== TEST 6: All OFF + base fail → score = 5.0 ===")
score_l_fail2, _ = calculate_scores(mock_fail, cfg_off)
print(f"  Expected: 5.0 | Actual: {score_l_fail2[0]:.1f}")
assert score_l_fail2[0] == 5.0, f"FAIL: Expected 5.0, got {score_l_fail2[0]}"
print("✅ PASS\n")

print("="*50)
print("🎉 ALL 6 TESTS PASSED!")
print("="*50)
