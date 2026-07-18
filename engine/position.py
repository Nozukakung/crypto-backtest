"""
engine/position.py — Position Manager v6 (Dynamic DCA Spacing)

เพิ่ม:
- Dynamic DCA Spacing: ระยะห่างขยายขึ้นเรื่อยๆ ตามจำนวนไม้ DCA
  ไม้ 1: ห่าง 0.3% | ไม้ 2: ห่าง 0.6% | ไม้ 3: ห่าง 1.2% | ...
- ป้องกันการถัวเร็วเกินไปในช่วง Bull Run
"""
from dataclasses import dataclass
from typing import List


@dataclass
class TradeRecord:
    timestamp: str
    action: str
    price: float
    size_usd: float
    fee_usd: float
    funding_usd: float = 0.0


class Position:
    def __init__(self, symbol, side, initial_size_usd, config):
        self.symbol = symbol
        self.side = side
        self.initial_size_usd = initial_size_usd
        self.config = config
        self.leverage = config.get("leverage", 5)
        self.status = "OPEN"
        self.records: List[TradeRecord] = []
        self.dca_count = 0
        self.total_size_usd = 0.0
        self.total_qty = 0.0
        self.total_fees_usd = 0.0
        self.total_funding_usd = 0.0
        self.holding_time_minutes = 0
        self.liquidated = False
        self.liquidation_price = 0.0
        self.merged_orders = False

        # Dynamic DCA Spacing
        self.dca_base_distance_pct = config.get("dca_trigger_below_bep_percent", 0.3) / 100.0
        self.dca_multiplier = config.get("dca_multiplier", 2.0)  # ขยาย distance × multiplier ทุกไม้
        self.dca_max_cap_usd = config.get("dca_max_cap_usd", 50000.0)

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
            self.merged_orders = False

    def apply_funding(self, funding_usd):
        self.total_funding_usd += funding_usd

    @property
    def entry_price(self):
        return self.total_size_usd / self.total_qty if self.total_qty > 0 else 0.0

    @property
    def margin_used(self):
        return self.total_size_usd / self.leverage

    @property
    def bep(self):
        """BEP = entry_price + (total_costs) / qty"""
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
        tp_offset = self.config.get("take_profit_above_bep_percent", 0.2) / 100.0
        if self.side == "LONG":
            return self.bep * (1.0 + tp_offset)
        else:
            return self.bep * (1.0 - tp_offset)

    @property
    def current_dca_distance_pct(self):
        """
        Dynamic DCA Distance:
        ไม้ที่ 0 (ครั้งแรกที่ DCA): base_distance (0.3%)
        ไม้ที่ 1: base_distance × multiplier (0.6%)
        ไม้ที่ 2: base_distance × multiplier^2 (1.2%)
        ไม้ที่ 3: base_distance × multiplier^3 (2.4%)
        ฯลฯ
        """
        return self.dca_base_distance_pct * (self.dca_multiplier ** self.dca_count)

    def check_dca_trigger(self, current_price):
        """
        Dynamic DCA trigger:
        ห่างจาก BEP มากกว่า current_dca_distance_pct → DCA
        """
        if self.total_size_usd + self.initial_size_usd > self.dca_max_cap_usd:
            return False

        if self.side == "LONG":
            if current_price >= self.bep:
                return False
            pct_under = (self.bep - current_price) / self.bep
            return pct_under > self.current_dca_distance_pct
        else:
            if current_price <= self.bep:
                return False
            pct_above = (current_price - self.bep) / self.bep
            return pct_above > self.current_dca_distance_pct

    def check_tp_trigger(self, current_price):
        if self.side == "LONG":
            return current_price >= self.take_profit_price
        else:
            return current_price <= self.take_profit_price

    def update_liquidation_price(self):
        if self.side == "LONG":
            self.liquidation_price = self.entry_price * (1.0 - 1.0 / self.leverage)
        else:
            self.liquidation_price = self.entry_price * (1.0 + 1.0 / self.leverage)

    def check_liquidation(self, current_price):
        if self.liquidation_price == 0.0:
            self.update_liquidation_price()
        if self.side == "LONG":
            return current_price <= self.liquidation_price
        else:
            return current_price >= self.liquidation_price

    def close(self, timestamp, exit_price, fee_rate):
        self.status = "CLOSED"
        exit_fee = self.total_size_usd * fee_rate
        self.total_fees_usd += exit_fee
        self.records.append(TradeRecord(
            timestamp=timestamp, action="CLOSE", price=exit_price,
            size_usd=self.total_size_usd, fee_usd=exit_fee
        ))
        return exit_fee

    def liquidate(self, timestamp, liq_price, fee_rate):
        self.status = "LIQUIDATED"
        self.liquidated = True
        self.records.append(TradeRecord(
            timestamp=timestamp, action="LIQUIDATE", price=liq_price,
            size_usd=self.total_size_usd, fee_usd=0.0
        ))
        return self.margin_used

    def update_time(self):
        self.holding_time_minutes += 1

    def pnl(self, exit_price):
        if self.side == "LONG":
            gross = (exit_price - self.entry_price) * self.total_qty
        else:
            gross = (self.entry_price - exit_price) * self.total_qty
        return gross - self.total_fees_usd - self.total_funding_usd

    def merge_orders(self, timestamp, fee_rate):
        self.merged_orders = True
        return True