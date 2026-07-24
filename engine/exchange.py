"""
engine/exchange.py — Exchange Rules (Lot Size, Tick Size, Precision)
จำลองกฎการเทรดจริงของ Binance/Bitget Futures
"""
from dataclasses import dataclass
from typing import Dict


@dataclass
class ExchangeSymbolInfo:
    symbol: str
    price_precision: int      # ทศนิยมราคา (Tick Size)
    qty_precision: int        # ทศนิยมจำนวน (Lot Size)
    min_qty: float            # จำนวนขั้นต่ำ
    min_notional: float       # มูลค่าขั้นต่ำ (USD)


# กฎจริงจาก Binance USD-M Futures (ตัวอย่าง)
EXCHANGE_RULES: Dict[str, ExchangeSymbolInfo] = {
    "BTCUSDT": ExchangeSymbolInfo(
        symbol="BTCUSDT",
        price_precision=1,      # ราคา 0.1 (เช่น 60123.4)
        qty_precision=3,        # จำนวน 0.001 BTC
        min_qty=0.001,
        min_notional=100.0
    ),
    "ETHUSDT": ExchangeSymbolInfo(
        symbol="ETHUSDT",
        price_precision=2,      # ราคา 0.01
        qty_precision=3,        # จำนวน 0.001 ETH
        min_qty=0.001,
        min_notional=100.0
    ),
    "BNBUSDT": ExchangeSymbolInfo(
        symbol="BNBUSDT",
        price_precision=2,      # ราคา 0.01
        qty_precision=2,        # จำนวน 0.01 BNB
        min_qty=0.01,
        min_notional=100.0
    ),
    "DOGEUSDT": ExchangeSymbolInfo(
        symbol="DOGEUSDT",
        price_precision=5,      # ราคา 0.00001
        qty_precision=0,        # จำนวนเต็ม DOGE (833, 834)
        min_qty=1.0,
        min_notional=8.0
    ),
    "SOLUSDT": ExchangeSymbolInfo(
        symbol="SOLUSDT",
        price_precision=3,      # ราคา 0.001
        qty_precision=1,        # จำนวน 0.1 SOL
        min_qty=0.1,
        min_notional=100.0
    ),
    "XRPUSDT": ExchangeSymbolInfo(
        symbol="XRPUSDT",
        price_precision=4,      # ราคา 0.0001
        qty_precision=1,        # จำนวน 0.1 XRP
        min_qty=0.1,
        min_notional=100.0
    ),
}


def get_symbol_info(symbol: str) -> ExchangeSymbolInfo:
    """ดึงกฎของเหรียญ (Default คือ 3 ตำแหน่งทศนิยม)"""
    return EXCHANGE_RULES.get(symbol, ExchangeSymbolInfo(
        symbol=symbol,
        price_precision=2,
        qty_precision=3,
        min_qty=0.001,
        min_notional=100.0
    ))


def round_to_precision(value: float, precision: int) -> float:
    """ปัดเศษตามทศนิยมที่กำหนด"""
    if precision < 0:
        # ปัดเป็นหลักสิบ/ร้อย (เช่น precision=-1 = ปัดเป็น 10)
        factor = 10 ** abs(precision)
        return round(value / factor) * factor
    return round(value, precision)


def calculate_qty_for_notional(
    symbol: str,
    notional_usd: float,
    price: float
) -> float:
    """
    คำนวณจำนวนที่สั่งให้ตรงกับ notional_usd พอดี
    โดยปัดเศษตาม qty_precision ของ Exchange
    """
    info = get_symbol_info(symbol)
    raw_qty = notional_usd / price
    rounded_qty = round_to_precision(raw_qty, info.qty_precision)
    
    # ตรวจสอบ min_qty
    if rounded_qty < info.min_qty:
        rounded_qty = info.min_qty
    
    return rounded_qty


def calculate_actual_notional(
    symbol: str,
    qty: float,
    price: float
) -> float:
    """คำนวณมูลค่าจริงหลังปัดเศษจำนวน"""
    return qty * price


def round_price(symbol: str, price: float) -> float:
    """ปัดเศษราคาตาม Tick Size ของ Exchange"""
    info = get_symbol_info(symbol)
    return round_to_precision(price, info.price_precision)