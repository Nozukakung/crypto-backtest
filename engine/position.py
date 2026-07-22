"""
engine/position.py — Position Manager v7 (Exchange Precision Rules)
"""
from dataclasses import dataclass
from typing import List
from engine.exchange import round_price, calculate_qty_for_notional, calculate_actual_notional


@dataclass
class TradeRecord:
    timestamp: str
    action: str
    price: float
    qty: float
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

        # DCA Parameters
        self.dca_base_distance_pct = config.get("dca_trigger_below_bep_percent", 0.3) / 100.0
        self.dca_multiplier = config.get("dca_multiplier", 1.0)
        self.dca_max_cap_usd = config.get("dca_max_cap_usd", 30000.0)

    def add_trade(self, timestamp, action, price, target_size_usd, fee_rate):
        # 1) ปัดเศษราคาตาม Tick Size
        price = round_price(self.symbol, price)
        
        # 2) คำนวณ qty ตาม Lot Size
        qty = calculate_qty_for_notional(self.symbol, target_size_usd, price)
        
        # 3) มูลค่าจริงที่สั่ง (หลังปัดเศษ)
        actual_size_usd = calculate_actual_notional(self.symbol, qty, price)
        
        # 4) คิดค่าธรรมเนียมจริง
        fee_usd = actual_size_usd * fee_rate
        
        self.total_size_usd += actual_size_usd
        self.total_qty += qty
        self.total_fees_usd += fee_usd
        
        self.records.append(TradeRecord(
            timestamp=timestamp, action=action, price=price, qty=qty,
            size_usd=actual_size_usd, fee_usd=fee_usd
        ))
        
        if action == "DCA":
            self.dca_count += 1
        if action in ("OPEN", "DCA"):
            self.merged_orders = False

    def apply_funding(self, funding_usd):
        self.total_funding_usd += funding_usd

    @property
    def entry_price(self):
        if self.total_qty == 0:
            return 0.0
        # ปัดเศษราคาเฉลี่ย
        return round_price(self.symbol, self.total_size_usd / self.total_qty)

    @property
    def margin_used(self):
        return self.total_size_usd / self.leverage

    @property
    def bep(self):
        if self.total_qty == 0:
            return 0.0
        total_costs = self.total_fees_usd + self.total_funding_usd
        cost_per_qty = total_costs / self.total_qty
        if self.side == "LONG":
            raw_bep = self.entry_price + cost_per_qty
        else:
            raw_bep = self.entry_price - cost_per_qty
        return round_price(self.symbol, raw_bep)

    @property
    def take_profit_price(self):
        tp_offset = self.config.get("take_profit_above_bep_percent", 0.2) / 100.0
        if self.side == "LONG":
            tp = self.bep * (1.0 + tp_offset)
        else:
            tp = self.bep * (1.0 - tp_offset)
        return round_price(self.symbol, tp)

    @property
    def current_dca_distance_pct(self):
        return self.dca_base_distance_pct * (self.dca_multiplier ** self.dca_count)

    def check_dca_trigger(self, current_price):
        # ตรวจสอบ Cap: total_size_usd รวมไม้แรกอยู่แล้ว
        # ใช้ >= ป้องกันทะลุ Cap
        if self.total_size_usd >= self.dca_max_cap_usd:
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

    def update_liquidation_price(self, portfolio_equity=0.0):
        """Cross Margin Liquidation: Liq = entry ± (equity / qty)
        ถ้า portfolio_equity = 0 → fallback เป็น Isolated Margin (เดิม)"""
        if self.total_qty == 0:
            return
        if portfolio_equity > 0:
            # Cross Margin: equity ทั้งพอร์ตค้ำ position นี้
            margin_per_qty = portfolio_equity / self.total_qty
            if self.side == "LONG":
                liq = self.entry_price - margin_per_qty
            else:
                liq = self.entry_price + margin_per_qty
        else:
            # Fallback: Isolated Margin
            if self.side == "LONG":
                liq = self.entry_price * (1.0 - 1.0 / self.leverage)
            else:
                liq = self.entry_price * (1.0 + 1.0 / self.leverage)
        self.liquidation_price = round_price(self.symbol, liq)

    def check_liquidation(self, current_price):
        if self.liquidation_price == 0.0:
            self.update_liquidation_price()
        if self.side == "LONG":
            return current_price <= self.liquidation_price
        else:
            return current_price >= self.liquidation_price

    def close(self, timestamp, exit_price, fee_rate):
        self.status = "CLOSED"
        exit_price = round_price(self.symbol, exit_price)
        exit_fee = self.total_size_usd * fee_rate
        self.total_fees_usd += exit_fee
        self.records.append(TradeRecord(
            timestamp=timestamp, action="CLOSE", price=exit_price, qty=self.total_qty,
            size_usd=self.total_size_usd, fee_usd=exit_fee
        ))
        return exit_fee

    def liquidate(self, timestamp, liq_price, fee_rate):
        self.status = "LIQUIDATED"
        self.liquidated = True
        self.records.append(TradeRecord(
            timestamp=timestamp, action="LIQUIDATE", price=liq_price, qty=self.total_qty,
            size_usd=self.total_size_usd, fee_usd=0.0
        ))
        return self.margin_used

    def update_time(self):
        self.holding_time_minutes += 1

    def pnl(self, exit_price):
        exit_price = round_price(self.symbol, exit_price)
        if self.side == "LONG":
            gross = (exit_price - self.entry_price) * self.total_qty
        else:
            gross = (self.entry_price - exit_price) * self.total_qty
        return gross - self.total_fees_usd - self.total_funding_usd

