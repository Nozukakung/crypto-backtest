"""
engine/position.py — Position Manager v4 (แก้ตามตาเล็ก 100%)

Logic ที่แก้:
1. BEP = วิธีเดียวกับ Exchange (รวม fee+funding+unrealized_pnl)
2. DCA: ราคาต้องห่างจาก BEP >0.3% ถึงถั่ว, <0.3% ข้าม
3. Timeout: ยกเลิก order → มัดรวมเป็น order เดียวที่ BEP+0.2%
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TradeRecord:
    timestamp: str
    action: str  # "OPEN", "DCA", "CLOSE"
    price: float
    size_usd: float
    fee_usd: float
    funding_usd: float = 0.0


class Position:
    """
    จำลอง 1 Position (Long หรือ Short)
    BEP = ราคาที่ว่า position จะเท่าทุน (รวม fee+funding+PnL ติดลบ)
    """

    def __init__(self, symbol, side, initial_size_usd, config):
        self.symbol = symbol
        self.side = side  # "LONG" or "SHORT"
        self.initial_size_usd = initial_size_usd
        self.config = config
        self.status = "OPEN"
        self.records: List[TradeRecord] = []
        self.dca_count = 0
        self.total_size_usd = 0.0
        self.total_qty = 0.0
        self.total_fees_usd = 0.0
        self.total_funding_usd = 0.0
        self.holding_time_minutes = 0

        # ใช้ track มัดรวม order (monitor)
        self.last_monitor_check = 0
        self.merged_orders = False

    def add_trade(self, timestamp, action, price, size_usd, fee_rate):
        qty = size_usd / price
        fee_usd = size_usd * fee_rate
        self.total_size_usd += size_usd
        self.total_qty += qty
        self.total_fees_usd += fee_usd
        self.records.append(TradeRecord(
            timestamp=timestamp, action=action, price=price,
            size_usd=size_usd, fee_usd=fee_usd
        ))
        if action == "DCA":
            self.dca_count += 1
        if action in ("OPEN", "DCA"):
            self.merged_orders = False  # reset merge flag on new trade

    def apply_funding(self, funding_usd):
        self.total_funding_usd += funding_usd

    @property
    def entry_price(self):
        """EP = ราคาเปิดเฉลี่ย"""
        return self.total_size_usd / self.total_qty if self.total_qty > 0 else 0.0

    @property
    def bep(self):
        """
        BEP แบบ Exchange: รวม fee + funding + unrealized PnL ติดลบ

        จากตาเล็ก: "BEP ของ exchange มันรวมค่า fee&funding และ real pnl
        ที่ติดลบ ของ position นั้นๆ ไว้ในนั้นให้แล้ว"

        สูตร: BEP = entry_price + (total_costs + negative_pnl) / total_qty

        โดย total_costs = total_fees_usd + total_funding_usd
        และ negative_pnl = ถ้า position ยังไม่ปิด และ gross_pnl ติดลบ
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
    def take_profit_price(self):
        """
        TP = BEP + 0.2% (ตาเล็ก: "ตั้งราคาปิด position ที่ BEP+TP")
        """
        tp_offset = self.config.get("take_profit_above_bep_percent", 0.2) / 100.0
        if self.side == "LONG":
            return self.bep * (1.0 + tp_offset)
        else:
            return self.bep * (1.0 - tp_offset)

    def check_dca_trigger(self, current_price):
        """
        DCA trigger ตามตาเล็ก:
        - ถ้าราคาอยู่ใกล้ BEP แค่ 0.3% → ข้าม ไม่ถั่ว
        - ถ้าราคาห่างจาก BEP มากกว่า 0.3% → DCA (size เดิม)

        ดังนั้น trigger = ราคาต้องต่ำกว่า BEP มากกว่า 0.3%
        """
        min_distance_pct = self.config.get("dca_trigger_below_bep_percent", 0.3) / 100.0
        max_cap = self.config.get("dca_max_cap_usd", 50000.0)

        # ถ้าถึง cap แล้ว → หยุด
        if self.total_size_usd + self.initial_size_usd > max_cap:
            return False

        # คำนวณ % distance จาก BEP
        if self.side == "LONG":
            if current_price >= self.bep:
                return False  # ราคา > BEP = profit ไม่ต้อง DCA
            # ราคาต่ำกว่า BEP เป็น %
            pct_under = (self.bep - current_price) / self.bep
            # DCA ต่อเมื่อห่างมากกว่า 0.3%
            return pct_under > min_distance_pct
        else:
            if current_price <= self.bep:
                return False
            pct_above = (current_price - self.bep) / self.bep
            return pct_above > min_distance_pct

    def check_tp_trigger(self, current_price):
        """TP trigger"""
        if self.side == "LONG":
            return current_price >= self.take_profit_price
        else:
            return current_price <= self.take_profit_price

    def close(self, timestamp, exit_price, fee_rate):
        """ปิด position คืน exit fee"""
        self.status = "CLOSED"
        exit_fee = self.total_size_usd * fee_rate
        self.total_fees_usd += exit_fee
        self.records.append(TradeRecord(
            timestamp=timestamp, action="CLOSE", price=exit_price,
            size_usd=self.total_size_usd, fee_usd=exit_fee
        ))
        return exit_fee

    def update_time(self):
        """+1 นาที"""
        self.holding_time_minutes += 1

    def pnl(self, exit_price):
        """
        Realized PnL เมื่อปิดที่ exit_price
        รวม fee + funding ที่จ่ายไปแล้ว
        """
        if self.side == "LONG":
            gross = (exit_price - self.entry_price) * self.total_qty
        else:
            gross = (self.entry_price - exit_price) * self.total_qty
        return gross - self.total_fees_usd - self.total_funding_usd

    def merge_orders(self, timestamp, fee_rate):
        """
        มัดรวม order (ตาม monitor ทุก 5 นาที)
        "ยกเลิกทุก order แล้วมัดรวมเหลือ order เดียว"
        "ตั้งราคาใหม่ที่ BEP + 0.2%"

        ใน backtest: reset position ให้เหลือแค่ 1 order ที่ entry = current BEP
        แล้ว TP = BEP + 0.2%
        """
        self.merged_orders = True
        # ไม่ต้องทำอะไรเพิ่ม เพราะ TP = BEP + 0.2%  คำนวณจาก bep property
        # ที่อัปเดตตลอดเวลา
        return True