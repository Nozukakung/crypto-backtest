"""
engine/position.py — จัดการสถานะ Position การทำ DCA และคำนวณ BEP, TP
"""
from dataclasses import dataclass
from typing import List, Literal


@dataclass
class TradeRecord:
    """ประวัติการเปิด/加仓/ปิดไม้"""
    timestamp: str
    action: Literal["OPEN", "DCA", "TP", "TIMEOUT_EXIT", "FORCE_EXIT"]
    price: float
    size_usd: float
    fee_usd: float
    funding_usd: float = 0.0


class Position:
    """
    คลาสจัดการ Position 1 ตัว (ต่อ 1 คู่เงิน)
    รองรับการทำ DCA แบบไม้เท่ากัน (Fixed Size)
    """
    def __init__(self, symbol: str, side: Literal["LONG", "SHORT"], initial_size_usd: float, config: dict):
        self.symbol = symbol
        self.side = side
        self.initial_size_usd = initial_size_usd
        self.config = config

        self.status = "OPEN"
        self.records: List[TradeRecord] = []
        self.dca_count = 0

        # ค่าสะสมเพื่อหา BEP (Break-Even Point)
        self.total_size_usd = 0.0
        self.total_qty = 0.0
        self.total_fees_usd = 0.0
        self.total_funding_usd = 0.0

        # เวลาถือครอง (minutes)
        self.holding_time_minutes = 0

    def add_trade(self, timestamp: str, action: Literal["OPEN", "DCA"], price: float, size_usd: float, fee_rate: float):
        """เพิ่มไม้เปิดหรือ DCA"""
        # คำนวณจำนวนเหรียญที่ได้
        qty = size_usd / price
        fee_usd = size_usd * fee_rate

        self.total_size_usd += size_usd
        self.total_qty += qty
        self.total_fees_usd += fee_usd

        # บันทึกประวัติ
        record = TradeRecord(
            timestamp=timestamp,
            action=action,
            price=price,
            size_usd=size_usd,
            fee_usd=fee_usd,
        )
        self.records.append(record)

        if action == "DCA":
            self.dca_count += 1

    def apply_funding(self, funding_usd: float):
        """สะสม funding rate"""
        self.total_funding_usd += funding_usd
        if self.records:
            self.records[-1].funding_usd += funding_usd

    @property
    def entry_price(self) -> float:
        """ราคาเปิดเฉลี่ยเฉยๆ (EP)"""
        if self.total_qty == 0:
            return 0.0
        return self.total_size_usd / self.total_qty

    @property
    def bep(self) -> float:
        """
        คำนวณ Break-Even Point (BEP) จริงตามนิยามในสูตร:
        BEP = ราคาเปิดเฉลี่ย + (ค่าใช้จ่ายทั้งหมด / จำนวนเหรียญ)
        """
        if self.total_qty == 0:
            return 0.0
        total_costs = self.total_fees_usd + self.total_funding_usd
        cost_per_qty = total_costs / self.total_qty

        if self.side == "LONG":
            return self.entry_price + cost_per_qty
        else:
            return self.entry_price - cost_per_qty

    @property
    def take_profit_price(self) -> float:
        """
        ราคา Take Profit:
        TP = BEP + 0.2% (สำหรับ LONG)
        TP = BEP - 0.2% (สำหรับ SHORT)
        """
        tp_offset = self.config.get("take_profit_above_bep_percent", 0.2) / 100.0
        if self.side == "LONG":
            return self.bep * (1.0 + tp_offset)
        else:
            return self.bep * (1.0 - tp_offset)

    def check_dca_trigger(self, current_price: float) -> bool:
        """
        ตรวจสอบเงื่อนไขการ DCA (ราคาต่ำกว่า BEP 0.3%)
        """
        dca_offset = self.config.get("dca_trigger_below_bep_percent", 0.3) / 100.0
        max_cap = self.config.get("dca_max_cap_usd", 50000.0)

        # เกินเพดานสูงสุดหรือไม่
        if self.total_size_usd + self.initial_size_usd > max_cap:
            return False

        if self.side == "LONG":
            # ราคาตกต่ำกว่า BEP
            return current_price <= self.bep * (1.0 - dca_offset)
        else:
            # ราคาสูงเกินกว่า BEP (สำหรับ SHORT)
            return current_price >= self.bep * (1.0 + dca_offset)

    def check_tp_trigger(self, current_price: float) -> bool:
        """
        ตรวจสอบเงื่อนไขการ Take Profit (TP)
        """
        if self.side == "LONG":
            return current_price >= self.take_profit_price
        else:
            return current_price <= self.take_profit_price

    def check_timeout_trigger(self) -> bool:
        """
        ตรวจสอบเงื่อนไขการหมดเวลา (Long 30 นาที, Short 120 นาที)
        """
        if self.side == "LONG":
            return self.holding_time_minutes >= self.config.get("long_timeout_minutes", 30)
        else:
            return self.holding_time_minutes >= self.config.get("short_timeout_minutes", 120)

    def close(self, timestamp: str, price: float, fee_rate: float, reason: Literal["TP", "TIMEOUT_EXIT", "FORCE_EXIT"]):
        """ปิดออเดอร์ทั้งหมด"""
        self.status = "CLOSED"
        fee_usd = self.total_size_usd * fee_rate
        self.total_fees_usd += fee_usd

        record = TradeRecord(
            timestamp=timestamp,
            action=reason,
            price=price,
            size_usd=self.total_size_usd,
            fee_usd=fee_usd,
        )
        self.records.append(record)

    def update_time(self):
        """อัปเดตระยะเวลาถือครอง"""
        self.holding_time_minutes += 1

    def pnl(self, current_price: float) -> float:
        """คำนวณกำไร/ขาดทุนปัจจุบัน (Unrealized PnL)"""
        if self.side == "LONG":
            val = self.total_qty * current_price
            return val - self.total_size_usd - self.total_fees_usd - self.total_funding_usd
        else:
            val = self.total_qty * (self.entry_price * 2 - current_price)
            # แก้สูตร Short PnL ให้ถูกต้อง
            return (self.entry_price - current_price) * self.total_qty - self.total_fees_usd - self.total_funding_usd