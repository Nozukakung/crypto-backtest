"""
backtest/portfolio.py — ติดตาม Equity Curve, คำนวณ Drawdown, จัดการทุน
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List


@dataclass
class TradeLog:
    """บันทึกการเทรด 1 ครั้ง"""
    symbol: str
    side: str
    open_time: str
    close_time: str
    ep: float           # entry price เฉลี่ย
    bep: float
    tp: float
    dca_count: int
    pnl_usd: float
    pnl_pct: float
    fee_usd: float
    holding_minutes: int
    close_reason: str


class Portfolio:
    """
    จัดการ Portfolio ทั้งหมด:
    - equity curve
    - trade log
    - drawdown tracking
    """
    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.equity_curve: List[dict] = []
        self.trade_logs: List[TradeLog] = []
        self.peak_equity = initial_capital
        self.max_drawdown_pct = 0.0

    def update_equity(self, timestamp: str, unrealized_pnl: float = 0.0):
        """อัปเดต equity (ทุน + unrealized pnl)"""
        equity = self.capital + unrealized_pnl
        self.equity_curve.append({
            "timestamp": timestamp,
            "capital": self.capital,
            "equity": equity,
            "unrealized_pnl": unrealized_pnl,
        })

        # คำนวณ drawdown
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = (self.peak_equity - equity) / self.peak_equity * 100
        if dd > self.max_drawdown_pct:
            self.max_drawdown_pct = dd

    def record_trade(self, trade: TradeLog):
        """บันทึกการเทรดที่ปิดแล้ว"""
        self.trade_logs.append(trade)
        self.capital += trade.pnl_usd

    def get_stats(self) -> dict:
        """คำนวณสถิติทั้งหมด"""
        if not self.trade_logs:
            return {"error": "No trades recorded"}

        trades = self.trade_logs
        pnls = np.array([t.pnl_usd for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        stats = {
            "total_trades": len(trades),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": len(wins) / len(trades) * 100 if trades else 0,
            "total_pnl_usd": float(pnls.sum()),
            "total_pnl_pct": float(pnls.sum() / self.initial_capital * 100),
            "avg_pnl_usd": float(pnls.mean()),
            "avg_win_usd": float(wins.mean()) if len(wins) > 0 else 0,
            "avg_loss_usd": float(losses.mean()) if len(losses) > 0 else 0,
            "max_drawdown_pct": self.max_drawdown_pct,
            "final_equity": self.capital,
            "total_fees_usd": sum(t.fee_usd for t in trades),
            "avg_holding_minutes": np.mean([t.holding_minutes for t in trades]),
            "avg_dca_count": np.mean([t.dca_count for t in trades]),
            "max_dca_count": max(t.dca_count for t in trades),
        }
        return stats

    def to_dataframe(self) -> pd.DataFrame:
        """แปลง equity curve เป็น DataFrame"""
        return pd.DataFrame(self.equity_curve)

    def trades_to_dataframe(self) -> pd.DataFrame:
        """แปลง trade logs เป็น DataFrame"""
        return pd.DataFrame([
            {
                "symbol": t.symbol,
                "side": t.side,
                "open_time": t.open_time,
                "close_time": t.close_time,
                "ep": t.ep,
                "bep": t.bep,
                "tp": t.tp,
                "dca_count": t.dca_count,
                "pnl_usd": t.pnl_usd,
                "pnl_pct": t.pnl_pct,
                "fee_usd": t.fee_usd,
                "holding_minutes": t.holding_minutes,
                "close_reason": t.close_reason,
            }
            for t in self.trade_logs
        ])