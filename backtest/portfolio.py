"""
backtest/portfolio.py — Equity Curve แบบ realizes PnL เท่านั้น
(ไม่ track unrealized ตอนถือ position — เหมือนตาเล็ก)
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List


@dataclass
class TradeLog:
    symbol: str
    side: str
    open_time: str
    close_time: str
    ep: float
    bep: float
    tp: float
    dca_count: int
    pnl_usd: float
    pnl_pct: float
    fee_usd: float
    holding_minutes: int
    close_reason: str


class Portfolio:
    def __init__(self, initial_capital=10000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.equity_curve = []
        self.trade_logs: List[TradeLog] = []
        self.peak_equity = initial_capital
        self.max_drawdown_pct = 0.0
        self.max_drawdown_usd = 0.0

    def update_equity(self, timestamp, realized_pnl=0.0):
        """
        อัปเดต equity = capital + realized_pnl积累
        สำคัญ: ไม่ track unrealized PnL (ตอนถือ position)
        """
        equity = self.capital  # equity = capital เท่านั้น (realized)
        self.equity_curve.append({
            "timestamp": timestamp,
            "equity": round(equity, 2),
        })
        # Drawdown
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd_pct = (self.peak_equity - equity) / self.peak_equity * 100 if self.peak_equity > 0 else 0
        dd_usd = self.peak_equity - equity
        if dd_pct > self.max_drawdown_pct:
            self.max_drawdown_pct = dd_pct
            self.max_drawdown_usd = dd_usd

    def record_trade(self, trade: TradeLog):
        self.trade_logs.append(trade)
        self.capital += trade.pnl_usd  # capital เพิ่ม/ลด จาก realized PnL เท่านั้น

    def get_stats(self):
        if not self.trade_logs:
            return {"error": "No trades"}
        trades = self.trade_logs
        pnls = np.array([t.pnl_usd for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        return {
            "total_trades": len(trades),
            "win_count": int(len(wins)),
            "loss_count": int(len(losses)),
            "win_rate": float(len(wins) / len(trades) * 100),
            "total_pnl_usd": float(pnls.sum()),
            "total_pnl_pct": float(pnls.sum() / self.initial_capital * 100),
            "final_equity": float(self.capital),
            "max_drawdown_pct": float(self.max_drawdown_pct),
            "max_drawdown_usd": float(self.max_drawdown_usd),
            "total_fees_usd": float(sum(t.fee_usd for t in trades)),
            "avg_holding_minutes": float(np.mean([t.holding_minutes for t in trades])),
            "avg_dca_count": float(np.mean([t.dca_count for t in trades])),
            "max_dca_count": int(max(t.dca_count for t in trades)),
        }

    def to_dataframe(self):
        df = pd.DataFrame(self.equity_curve)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def trades_to_dataframe(self):
        return pd.DataFrame([
            {
                "symbol": t.symbol, "side": t.side,
                "open_time": t.open_time, "close_time": t.close_time,
                "ep": t.ep, "bep": t.bep, "tp": t.tp,
                "dca_count": t.dca_count,
                "pnl_usd": t.pnl_usd, "pnl_pct": t.pnl_pct,
                "fee_usd": t.fee_usd, "holding_minutes": t.holding_minutes,
                "close_reason": t.close_reason,
            } for t in self.trade_logs
        ])