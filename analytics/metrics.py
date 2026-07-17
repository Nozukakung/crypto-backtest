"""
analytics/metrics.py — คำนวณสถิติขั้นสูงสำหรับ Backtest
"""
import numpy as np
import pandas as pd
from typing import Dict, List


def calculate_advanced_metrics(stats: dict, equity_df: pd.DataFrame, trades_df: pd.DataFrame) -> dict:
    """
    คำนวณสถิติขั้นสูง: Sharpe, Sortino, Calmar, Profit Factor ฯลฯ
    """
    if equity_df.empty or len(equity_df) < 2:
        return {"error": "ข้อมูลไม่เพียงพอ"}

    # Returns ต่อช่วงเวลา (per candle)
    equity = equity_df["equity"].values
    returns = np.diff(equity) / equity[:-1]

    # Sharpe Ratio (annualized, assume 1m candle = 525600 periods/year)
    if returns.std() > 0:
        sharpe = np.mean(returns) / returns.std() * np.sqrt(525600)
    else:
        sharpe = 0.0

    # Sortino Ratio
    downside = returns[returns < 0]
    if downside.std() > 0:
        sortino = np.mean(returns) / downside.std() * np.sqrt(525600)
    else:
        sortino = 0.0

    # Calmar Ratio
    max_dd = stats.get("max_drawdown_pct", 0)
    annual_return = stats.get("total_pnl_pct", 0)  # สมมติเป็น annual
    calmar = annual_return / max_dd if max_dd > 0 else 0.0

    # Profit Factor
    wins = trades_df[trades_df["pnl_usd"] > 0]["pnl_usd"].sum()
    losses = abs(trades_df[trades_df["pnl_usd"] < 0]["pnl_usd"].sum())
    profit_factor = wins / losses if losses > 0 else float('inf')

    # Win/Loss ratio
    if len(trades_df) > 0:
        avg_win = trades_df[trades_df["pnl_usd"] > 0]["pnl_usd"].mean() if (trades_df["pnl_usd"] > 0).any() else 0
        avg_loss = abs(trades_df[trades_df["pnl_usd"] < 0]["pnl_usd"].mean()) if (trades_df["pnl_usd"] < 0).any() else 0
        win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')
    else:
        win_loss_ratio = 0.0

    # Expectancy
    expectancy = stats.get("avg_pnl_usd", 0) if "avg_pnl_usd" in stats else 0

    # Max consecutive wins/losses
    if len(trades_df) > 0:
        pnls = trades_df["pnl_usd"].values
        curr_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        for p in pnls:
            if p > 0:
                if curr_streak > 0:
                    curr_streak += 1
                else:
                    curr_streak = 1
                max_win_streak = max(max_win_streak, curr_streak)
            elif p < 0:
                if curr_streak < 0:
                    curr_streak -= 1
                else:
                    curr_streak = -1
                max_loss_streak = max(max_loss_streak, abs(curr_streak))
            else:
                curr_streak = 0
    else:
        max_win_streak = 0
        max_loss_streak = 0

    return {
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "profit_factor": profit_factor,
        "win_loss_ratio": win_loss_ratio,
        "expectancy_usd": expectancy,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "annualized_return_pct": annual_return,
    }


def monthly_returns(equity_df: pd.DataFrame) -> pd.DataFrame:
    """คำนวณผลตอบแทนรายเดือน"""
    if equity_df.empty:
        return pd.DataFrame()

    df = equity_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["month"] = df["timestamp"].dt.to_period("M")

    monthly = df.groupby("month")["equity"].agg(["first", "last", "max", "min"])
    monthly["return_pct"] = (monthly["last"] - monthly["first"]) / monthly["first"] * 100
    monthly["max_dd_pct"] = (monthly["max"] - monthly["min"]) / monthly["max"] * 100

    return monthly.reset_index()


def yearly_returns(equity_df: pd.DataFrame) -> pd.DataFrame:
    """คำนวณผลตอบแทนรายปี"""
    if equity_df.empty:
        return pd.DataFrame()

    df = equity_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["year"] = df["timestamp"].dt.to_period("Y")

    yearly = df.groupby("year")["equity"].agg(["first", "last", "max", "min"])
    yearly["return_pct"] = (yearly["last"] - yearly["first"]) / yearly["first"] * 100
    yearly["max_dd_pct"] = (yearly["max"] - yearly["min"]) / yearly["max"] * 100

    return yearly.reset_index()


def trade_distribution(trades_df: pd.DataFrame) -> Dict[str, pd.Series]:
    """แจกจงการเทรดตามช่วงเวลา/ผลกำไร"""
    if trades_df.empty:
        return {}

    df = trades_df.copy()
    df["open_time"] = pd.to_datetime(df["open_time"])
    df["hour"] = df["open_time"].dt.hour

    # Distribution by hour
    by_hour = df.groupby("hour")["pnl_usd"].sum()

    # Distribution by side
    by_side = df.groupby("side")["pnl_usd"].sum()

    # Distribution by DCA count
    by_dca = df.groupby("dca_count")["pnl_usd"].sum()

    return {
        "by_hour": by_hour,
        "by_side": by_side,
        "by_dca": by_dca,
    }