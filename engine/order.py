"""
engine/order.py — ระบบ Order (Maker limit order + กลไก refresh ทุก 1 นาที)
"""
from dataclasses import dataclass
from typing import Literal
from engine.position import Position


@dataclass
class Order:
    """จำลองออเดอร์"""
    timestamp: str
    side: Literal["BUY", "SELL"]
    price: float
    size_usd: float
    status: Literal["PENDING", "FILLED", "CANCELLED"]

    def cancel(self):
        self.status = "CANCELLED"


def maker_price(current_price: float, side: str, offset_pct: float = 0.05) -> float:
    """
    คำนวณราคา Maker limit order:
    LONG:  ราคา = ราคาปัจจุบัน − 0.05% (จะได้เป็น Maker แน่ๆ)
    SHORT: ราคา = ราคาปัจจุบัน + 0.05%
    """
    offset = offset_pct / 100.0
    if side == "LONG":
        return current_price * (1.0 - offset)
    else:
        return current_price * (1.0 + offset)


def check_order_match(order_price: float, current_price: float, side: str) -> bool:
    """
    ตรวจสอบว่าออเดอร์ match กับราคาปัจจุบันหรือไม่
    LONG:  match เมื่อราคาตกลงมาถึงหรือต่ำกว่า
    SHORT: match เมื่อราคาขึ้นมาถึงหรือสูงกว่า
    """
    if side == "LONG":
        return current_price <= order_price
    else:
        return current_price >= order_price


class OrderManager:
    """
    จัดการออเดอร์ทั้งหมด:
    - สร้างออเดอร์จาก signal
    - ตรวจสอบสถานะ (match/cancel)
    - สร้างออเดอร์ใหม่ถ้าราคาขยับ
    """
    def __init__(self, config: dict):
        self.fee_rate_maker = config.get("fee_rate_maker", 0.0002) / 100.0
        self.fee_rate_taker = config.get("fee_rate_taker", 0.00045) / 100.0
        self.offset_pct = config.get("price_offset_percent", 0.05)
        self.current_order: Order | None = None

    def create_order(self, timestamp: str, side: str, current_price: float, size_usd: float) -> Order:
        """
        สร้างออเดอร์ Maker ใหม่
        """
        order_side = "BUY" if side == "LONG" else "SELL"
        order_price = maker_price(current_price, side, self.offset_pct)
        order = Order(
            timestamp=timestamp,
            side=order_side,
            price=order_price,
            size_usd=size_usd,
            status="PENDING",
        )
        self.current_order = order
        return order

    def check_and_match(self, timestamp: str, current_price: float) -> bool:
        """
        ตรวจสอบว่าออเดอร์ที่ค้าง match กับราคาปัจจุบันหรือไม่
        ถ้า match → เปลี่ยนสถานะเป็น FILLED
        return True ถ้ามีออเดอร์ถูก fill
        """
        if self.current_order is None or self.current_order.status != "PENDING":
            return False

        if check_order_match(self.current_order.price, current_price, self.current_order.side):
            self.current_order.status = "FILLED"
            return True
        return False

    def cancel_and_create_new(self, timestamp: str, current_price: float, size_usd: float, side: str) -> Order:
        """
        ยกเลิกออเดอร์เก่า แล้วสร้างใหม่ตามราคาล่าสุด
        (กลไก refresh ทุก 1 นาที)
        """
        if self.current_order and self.current_order.status == "PENDING":
            self.current_order.cancel()
        return self.create_order(timestamp, side, current_price, size_usd)