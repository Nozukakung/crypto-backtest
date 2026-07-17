"""
engine/risk.py — ตรวจสอบความเสี่ยง (Max Position, Margin Call)
"""


def check_margin(position_total_size: float, capital: float,
                  max_leverage: float = float('inf')) -> bool:
    """
    ตรวจสอบว่า equity เพียงพอต่อ position size หรือไม่
    return False = พอร์ตแตก (ไม่พอ)
    """
    return position_total_size <= capital * max_leverage


def check_max_cap(position_total_size: float, max_cap: float) -> bool:
    """
    ตรวจสอบว่าเกิน Position Cap ($50K) หรือไม่
    return True = เกิน (ไม่ควรเปิดเพิ่ม)
    """
    return position_total_size > max_cap