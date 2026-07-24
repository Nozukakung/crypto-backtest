"""
backtest/runner.py — Backtest v6 (ตาเล็ก 100% Exact Match)
- DCA: เช็คสัญญาณเดียวกับไม้แรก (RSI + Pattern) + ห่าง BEP > 0.3%
- Monitor: มัดรวม = ตั้ง TP ที่ BEP+0.2% ไม่คัดทิ้ง (ไม่มี Stop Loss)
- PNL: รวม unrealized PnL
"""
import yaml
import pandas as pd
from pathlib import Path
from tqdm import tqdm

from data.store import load_parquet
from engine.indicators import compute_rsi, compute_bollinger_bands, compute_adx, compute_ema, compute_ibs, compute_volume_spike, compute_candle_features, detect_candle_patterns
from engine.position import Position
from backtest.portfolio import Portfolio, TradeLog


def _auto_save_results(symbol, result, cfg):
    """บันทึกผลลัพธ์ Backtest อัตโนมัติทุกครั้งที่รันเสร็จ"""
    from backtest.db import get_conn
    from datetime import datetime
    import json
    import os

    stats = result['stats']
    trades = result['trades']
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # 1. เขียนลง SQLite
    conn = get_conn()
    cursor = conn.cursor()
    
    # ดึงหรือสร้าง run_id
    # หา run_id ล่าสุด หรือสร้างใหม่ถ้ายังไม่มีในนาทีนี้
    run_timestamp_prefix = timestamp[:16] # "YYYY-MM-DD_HH-MM"
    cursor.execute("SELECT id FROM runs WHERE run_timestamp LIKE ? LIMIT 1", (f"{run_timestamp_prefix}%",))
    row = cursor.fetchone()
    
    if row:
        run_id = row[0]
    else:
        import hashlib
        config_hash = hashlib.md5(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]
        cursor.execute("""
            INSERT INTO runs (run_timestamp, run_name, config_hash)
            VALUES (?, ?, ?)
        """, (timestamp, timestamp.replace('_', ' '), config_hash))
        run_id = cursor.lastrowid

    # ลบข้อมูลเก่าของเหรียญนี้ทุก run_id (ไม่ให้ DB บวมจากการรันซ้ำหลายรอบ)
    cursor.execute("DELETE FROM trades WHERE symbol = ?", (symbol,))

    # Insert trades
    trades_list = trades.to_dict('records')
    for t in trades_list:
        # แปลง Timestamp เป็น string
        open_t = str(t.get('open_time')) if t.get('open_time') is not None else ''
        close_t = str(t.get('close_time')) if t.get('close_time') is not None else ''
        
        cursor.execute("""
            INSERT INTO trades (run_id, symbol, side, open_time, close_time, ep, bep, tp, dca_count, pnl_usd, pnl_pct, fee_usd, holding_minutes, close_reason, max_distance_pct, entry_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            symbol,
            t.get('side'),
            open_t,
            close_t,
            float(t.get('ep', 0)),
            float(t.get('bep', 0)),
            float(t.get('tp', 0)),
            int(t.get('dca_count', 0)),
            float(t.get('pnl_usd', 0)),
            float(t.get('pnl_pct', 0)),
            float(t.get('fee_usd', 0)),
            int(t.get('holding_minutes', 0)),
            t.get('close_reason'),
            float(t.get('max_distance_pct', 0)),
            float(t.get('entry_score', 0))
        ))

    # อัปเดต aggregate stats ของ run นี้
    cursor.execute("""
        UPDATE runs 
        SET 
            total_pnl_usd = (SELECT SUM(pnl_usd) FROM trades WHERE run_id = ?),
            total_trades = (SELECT COUNT(*) FROM trades WHERE run_id = ?),
            total_liquidations = (SELECT SUM(CASE WHEN close_reason='LIQUIDATE' THEN 1 ELSE 0 END) FROM trades WHERE run_id = ?),
            max_dca_any_symbol = (SELECT MAX(dca_count) FROM trades WHERE run_id = ?)
        WHERE id = ?
    """, (run_id, run_id, run_id, run_id, run_id))

    conn.commit()
    
    # Cleanup orphan runs (runs with no trades left)
    cursor.execute("DELETE FROM runs WHERE id NOT IN (SELECT DISTINCT run_id FROM trades)")
    conn.commit()
    
    # VACUUM ต้องอยู่นอกระบบ transaction
    conn.execute("VACUUM")
    conn.close()

    pnl = float(round(stats['total_pnl_usd'], 2))
    dd = float(round(stats['max_drawdown_pct'], 2))
    liq = int((trades['close_reason'] == 'LIQUIDATE').sum())
    max_dca = int(trades['dca_count'].max())
    trades_count = int(len(trades))
    print(f"💾 Saved to SQLite | PnL ${pnl:>8,.2f} | DD {dd:.2f}% | Max DCA {max_dca} | Liq {liq} | Trades {trades_count}")


CONFIG_PATH = Path(__file__).parent.parent / "config" / "strategy.yaml"


def load_config(path=None):
    with open(path or str(CONFIG_PATH)) as f:
        return yaml.safe_load(f)

def maker_price(price, side, offset_pct=0.05):
    offset = offset_pct / 100.0
    if side == "LONG":
        return price * (1.0 - offset)
    else:
        return price * (1.0 + offset)


def run_backtest(symbol, cfg=None):
    if cfg is None:
        cfg = load_config()

    strategy_cfg = cfg.get("strategy", {})
    signal_cfg = cfg.get("signal", {})
    order_cfg = cfg.get("order", {})
    position_cfg = cfg.get("position", {})

    capital = strategy_cfg.get("initial_capital", 10000.0)
    size_per_trade = strategy_cfg.get("size_per_trade_usd", 100.0)
    leverage = strategy_cfg.get("leverage", 10)
    
    # ส่ง leverage เข้า position_cfg
    position_cfg = position_cfg.copy()
    position_cfg["leverage"] = leverage
    
    cooldown_minutes = position_cfg.get("cooldown_minutes", 5)
    max_cap = position_cfg.get("dca_max_cap_usd", 50000.0)
    fee_rate = order_cfg.get("fee_rate_maker", 0.02) / 100.0
    offset_pct = order_cfg.get("price_offset_percent", 0.05)
    long_timeout = position_cfg.get("long_timeout_minutes", 30)
    short_timeout = position_cfg.get("short_timeout_minutes", 120)
    monitor_interval = position_cfg.get("monitor_interval_minutes", 5)
    cutloss_minutes = position_cfg.get("cutloss_after_stop_minutes", 4320)  # 3 วัน
    funding_rate_per_8h = position_cfg.get("funding_rate_per_8h", 0.01) / 100.0

    print(f"🔄 Loading {symbol}...")
    df = load_parquet(symbol)
    total_rows = len(df)
    print(f"   Rows: {total_rows:,}")

    # ====== Compute signals ======
    print(f"   Computing signals...")
    df["rsi"] = compute_rsi(df["close"].values, signal_cfg.get("rsi_period", 14))
    df["rsi_fast"] = compute_rsi(df["close"].values, signal_cfg.get("rsi_fast_period", 2))
    
    # IBS (Internal Bar Strength)
    df["ibs"] = compute_ibs(df["high"].values, df["low"].values, df["close"].values)
    
    # Volume Spike (ถ้ามี volume ข้อมูล)
    vol_spike_mult = signal_cfg.get("volume_spike_multiplier", 2.0)
    if "volume" in df.columns:
        df["vol_spike"] = compute_volume_spike(df["volume"].values, period=20, multiplier=vol_spike_mult)
    else:
        df["vol_spike"] = False
    
    # คำนวณ Bollinger Bands (BB)
    bb_period = signal_cfg.get("bb_period", 20)
    bb_std = signal_cfg.get("bb_std", 2.0)
    df["bb_upper"], df["bb_middle"], df["bb_lower"] = compute_bollinger_bands(df["close"].values, bb_period, bb_std)
    
    # คำนวณ ADX
    adx_period = signal_cfg.get("adx_period", 14)
    df["adx"], _, _ = compute_adx(df["high"].values, df["low"].values, df["close"].values, adx_period)
    
    # คำนวณ EMA Trend Filter
    ema_period = signal_cfg.get("ema_period", 10080)
    df["ema"] = compute_ema(df["close"].values, ema_period)
    
    df = compute_candle_features(df)
    df = detect_candle_patterns(df)

    # ====== READ ENABLE FLAGS ======
    adx_enabled = signal_cfg.get("adx_enabled", True)
    ema_enabled = signal_cfg.get("ema_enabled", True)
    ibs_enabled = signal_cfg.get("ibs_enabled", True)
    vol_spike_enabled = signal_cfg.get("vol_spike_enabled", True)

    # ====== READ SCORE WEIGHTS & THRESHOLD ======
    score_threshold = signal_cfg.get("score_threshold", 7.0)
    weights_cfg = signal_cfg.get("weights", {})
    w_bb = weights_cfg.get("bb", 3.0)
    w_rsi = weights_cfg.get("rsi", 2.0)
    w_ibs = weights_cfg.get("ibs", 2.0)
    w_vol = weights_cfg.get("vol_spike", 1.5)
    w_adx = weights_cfg.get("adx", 1.0)
    w_ema = weights_cfg.get("ema", 0.5)

    rsi_long = signal_cfg.get("rsi_long_threshold", 40.0)
    rsi_short = signal_cfg.get("rsi_short_threshold", 60.0)
    ibs_long = signal_cfg.get("ibs_long_threshold", 0.1)
    ibs_short = signal_cfg.get("ibs_short_threshold", 0.9)
    adx_limit = signal_cfg.get("adx_trend_limit", 20.0)

    # ====== SCORE-BASED ENTRY SYSTEM ======
    # Base = RSI + BB (ต้องผ่านพร้อมกันแบบ boolean)
    rsi_ok_long = df["rsi"] < rsi_long
    rsi_ok_short = df["rsi"] > rsi_short
    bb_ok_long = df["close"] < df["bb_lower"]
    bb_ok_short = df["close"] > df["bb_upper"]

    base_long = (rsi_ok_long.fillna(False) & bb_ok_long.fillna(False)).astype(float)
    base_short = (rsi_ok_short.fillna(False) & bb_ok_short.fillna(False)).astype(float)

    # เริ่มคำนวณคะแนน (Base: RSI + BB = w_rsi + w_bb)
    score_long = base_long * (w_rsi + w_bb)
    score_short = base_short * (w_rsi + w_bb)

    # ADX Score (ถ้าปิดใช้งานให้ได้คะแนนเต็ม)
    if adx_enabled:
        adx_ok = (df["adx"] < adx_limit).fillna(False).astype(float)
        score_long += adx_ok * w_adx
        score_short += adx_ok * w_adx
    else:
        score_long += w_adx
        score_short += w_adx

    # EMA Score
    if ema_enabled:
        ema_ok_long = (df["close"] > df["ema"]).fillna(False).astype(float)
        ema_ok_short = (df["close"] < df["ema"]).fillna(False).astype(float)
        score_long += ema_ok_long * w_ema
        score_short += ema_ok_short * w_ema
    else:
        score_long += w_ema
        score_short += w_ema

    # IBS Score
    if ibs_enabled:
        ibs_ok_long = (df["ibs"] < ibs_long).fillna(False).astype(float)
        ibs_ok_short = (df["ibs"] > ibs_short).fillna(False).astype(float)
        score_long += ibs_ok_long * w_ibs
        score_short += ibs_ok_short * w_ibs
    else:
        score_long += w_ibs
        score_short += w_ibs

    # Volume Spike Score
    if vol_spike_enabled:
        vol_ok = df["vol_spike"].fillna(False).astype(float)
        score_long += vol_ok * w_vol
        score_short += vol_ok * w_vol
    else:
        score_long += w_vol
        score_short += w_vol

    # เก็บคะแนนไว้ใน DataFrame สำหรับบันทึกลง DB
    df["entry_score_long"] = score_long
    df["entry_score_short"] = score_short

    # Final Signal: Score >= threshold AND Base must pass (base_long/base_short > 0)
    df["signal_long"] = (score_long >= score_threshold) & (base_long > 0)
    df["signal_short"] = (score_short >= score_threshold) & (base_short > 0)

    long_count = int(df["signal_long"].sum())
    short_count = int(df["signal_short"].sum())
    active_filters = ["RSI", "BB"]
    if adx_enabled: active_filters.append(f"ADX<{adx_limit}")
    if ema_enabled: active_filters.append(f"EMA={ema_period}")
    if ibs_enabled: active_filters.append("IBS")
    if vol_spike_enabled: active_filters.append("VolSpike")
    print(f"   Signals computed: LONG={long_count:,} | SHORT={short_count:,} (Score>={score_threshold}, {', '.join(active_filters)})")
    # ====== Simulate ======
    portfolio = Portfolio(initial_capital=capital)
    position = None
    active_order = None

    timestamps = df["timestamp"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    signal_long = df["signal_long"].values
    signal_short = df["signal_short"].values
    entry_score_long = df["entry_score_long"].values
    entry_score_short = df["entry_score_short"].values

    # สำหรับ Funding Rate (ทุก 8 ชม. = 480 นาที)
    funding_interval = 480  # นาที
    funding_tick = 0

    monitor_tick = 0
    cooldown_remaining = 0

    pbar = tqdm(total=total_rows, desc=f"   Simulating ({total_rows:,} candles)")

    for i in range(total_rows):
        ts = timestamps[i]
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        price = c

        # Funding Rate (ทุก 8 ชม.)
        funding_tick += 1
        if funding_tick >= funding_interval and position is not None and position.status == "OPEN":
            funding_tick = 0
            funding_usd = position.total_size_usd * funding_rate_per_8h
            position.apply_funding(funding_usd)

        # Cooldown
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            portfolio.update_equity(ts)
            pbar.update(1)
            continue

        monitor_tick += 1
        monitor_triggered = monitor_tick >= monitor_interval
        if monitor_triggered:
            monitor_tick = 0

        # ======= Has open position =======
        if position is not None and position.status == "OPEN":
            position.update_time()
            side = position.side
            
            # คำนวณ max_distance_pct แบบ absolute (ไม่ว่า LONG/SHORT)
            # = ราคาเบี่ยงสูงสุดจาก entry เท่าไหร่ในทิศทางที่เสียเปรียบ
            if side == "LONG":
                # LONG: low ลากลงไปไกลแค่ไหนจาก EP
                dist = abs(position.first_entry_price - min(l, position.first_entry_price)) / position.first_entry_price * 100
            else:
                # SHORT: high ลากขึ้นไปไกลแค่ไหนจาก EP
                dist = abs(max(h, position.first_entry_price) - position.first_entry_price) / position.first_entry_price * 100
            if dist > position.max_distance_pct:
                position.max_distance_pct = dist

            # 1) Liquidation Check
            if position.check_liquidation(l if side == "LONG" else h, portfolio.capital):
                liq_price = position.liquidation_price
                position.liquidate(ts, liq_price, fee_rate)
                pnl = position.pnl(liq_price)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp, close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price, dca_count=position.dca_count,
                    pnl_usd=round(pnl, 2),
                    pnl_pct=round(pnl / position.total_size_usd * 100, 4),
                    fee_usd=round(position.total_fees_usd, 2),
                    holding_minutes=position.holding_time_minutes,
                    max_distance_pct=round(position.max_distance_pct, 4),
                    entry_score=round(position.entry_score, 2),
                    close_reason="LIQUIDATE",
                ))
                portfolio.update_equity(ts)
                position = None
                active_order = None
                cooldown_remaining = cooldown_minutes
                pbar.update(1)
                continue

            # 2) TP Check
            if side == "LONG" and h >= position.take_profit_price:
                exit_price = position.take_profit_price
                position.close(ts, exit_price, fee_rate)
                pnl = position.pnl(exit_price)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp, close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price, dca_count=position.dca_count,
                    pnl_usd=round(pnl, 2),
                    pnl_pct=round(pnl / position.total_size_usd * 100, 4),
                    fee_usd=round(position.total_fees_usd, 2),
                    holding_minutes=position.holding_time_minutes,
                    max_distance_pct=round(position.max_distance_pct, 4),
                    entry_score=round(position.entry_score, 2),
                    close_reason="TP",
                ))
                portfolio.update_equity(ts)
                position = None
                active_order = None
                cooldown_remaining = cooldown_minutes
                pbar.update(1)
                continue

            if side == "SHORT" and l <= position.take_profit_price:
                exit_price = position.take_profit_price
                position.close(ts, exit_price, fee_rate)
                pnl = position.pnl(exit_price)
                portfolio.record_trade(TradeLog(
                    symbol=symbol, side=side,
                    open_time=position.records[0].timestamp, close_time=ts,
                    ep=position.entry_price, bep=position.bep,
                    tp=position.take_profit_price, dca_count=position.dca_count,
                    pnl_usd=round(pnl, 2),
                    pnl_pct=round(pnl / position.total_size_usd * 100, 4),
                    fee_usd=round(position.total_fees_usd, 2),
                    holding_minutes=position.holding_time_minutes,
                    max_distance_pct=round(position.max_distance_pct, 4),
                    entry_score=round(position.entry_score, 2),
                    close_reason="TP",
                ))
                portfolio.update_equity(ts)
                position = None
                active_order = None
                cooldown_remaining = cooldown_minutes
                pbar.update(1)
                continue

            # 3) Monitor (มัดรวม & Cut Loss)
            # Timeout (LONG 30 นาที, SHORT 120 นาที) -> หยุด DCA ทันที
            # หลังหยุด DCA (ไม่ว่าจะเพราะ Timeout หรือชน Cap) -> ถ้าเกิน 24 ชม. (1440 นาที) ยังไม่ TP -> Cut Loss
            if monitor_triggered:
                # 3.1) เช็ค Timeout
                timeout_hit = (side == "LONG" and position.holding_time_minutes >= long_timeout) or \
                             (side == "SHORT" and position.holding_time_minutes >= short_timeout)

                if timeout_hit and not position.dca_disabled:
                    position.dca_disabled = True
                    position.dca_disabled_at = ts

                # 3.2) เช็คชน Cap (ถ้าชน Cap ก็ให้ dca_disabled_at เริ่มทำงานถ้ายังไม่มีค่า)
                if position.total_size_usd >= max_cap and position.dca_disabled_at is None:
                    position.dca_disabled = True
                    position.dca_disabled_at = ts

                # 3.3) Cut Loss: เช็คเวลาหลังหยุดถัว เกิน 24 ชม. (1440 นาที) หรือไม่
                if position.dca_disabled and position.dca_disabled_at is not None:
                    # คำนวณความต่างเวลา (เนื่องจาก timestamp เป็น string/datetime เราใช้ holding_minutes หลังหยุดถัวเทียบง่ายกว่า)
                    # โดย dca_disabled_at เกิดที่ holding_minutes เท่าไหร่ -> ถ้าห่างเกิน 1440 นาที -> Cut Loss
                    # เพื่อความเป๊ะ เราบันทึกเวลาหยุดถัวโดยใช้ holding_minutes เป็นเกณฑ์
                    if not hasattr(position, "dca_disabled_at_minutes") or position.dca_disabled_at_minutes is None:
                        position.dca_disabled_at_minutes = position.holding_time_minutes

                    time_since_stop_dca = position.holding_time_minutes - position.dca_disabled_at_minutes
                    if time_since_stop_dca >= cutloss_minutes:  # Cut Loss
                        exit_price = maker_price(price, side, offset_pct)
                        position.close(ts, exit_price, fee_rate)
                        pnl = position.pnl(exit_price)
                        portfolio.record_trade(TradeLog(
                            symbol=symbol, side=side,
                            open_time=position.records[0].timestamp, close_time=ts,
                            ep=position.entry_price, bep=position.bep,
                            tp=position.take_profit_price, dca_count=position.dca_count,
                            pnl_usd=round(pnl, 2),
                            pnl_pct=round(pnl / position.total_size_usd * 100, 4),
                            fee_usd=round(position.total_fees_usd, 2),
                            holding_minutes=position.holding_time_minutes,
                            max_distance_pct=round(position.max_distance_pct, 4),
                            entry_score=round(position.entry_score, 2),
                    close_reason="CUTLOSS",
                        ))
                        portfolio.update_equity(ts)
                        position = None
                        active_order = None
                        cooldown_remaining = cooldown_minutes
                        pbar.update(1)
                        continue

            # 4) DCA Check — ถัวแค่ห่าง BEP > 0.3% + Cap ไม่เกิน
            if position.check_dca_trigger(l if side == "LONG" else h, portfolio.capital):
                dca_price = maker_price(price, side, offset_pct)
                position.add_trade(ts, "DCA", dca_price, size_per_trade, fee_rate)
                position.update_liquidation_price(portfolio.capital)
                active_order = {
                    "price": position.take_profit_price,
                    "side": "SELL" if side == "LONG" else "BUY",
                    "is_tp": True,
                }

            portfolio.update_equity(ts)
            pbar.update(1)
            continue

        # ======= Order Loop: จับคู่ Limit Order แรก (ไม่มี position ก็ทำงานได้) =======
        # ข้ามบล็อกนี้ถ้ามี pending order (ให้สัญญาณใหม่ทับได้เลย)

        # ======= No position → เช็ค Signal (Long + Short) =======
        # กฎ: ถ้า active_order ยัง pending อยู่ (is_tp=False) ห้ามทับ!
        # ปล่อยให้มันรอจนกว่า 10 นาที จะถูก cancel โดย stale logic หรือราคาชน
        if signal_long[i] and not position:
            # ถ้ามี pending order อยู่แล้ว → ข้าม ไม่ต้องตั้งใหม่
            if active_order and not active_order.get("is_tp"):
                pass
            else:
                order_price = maker_price(price, "LONG", offset_pct)
                if l <= order_price:
                    pos = Position(symbol, "LONG", size_per_trade, position_cfg)
                    pos.entry_score = entry_score_long[i]
                    pos.add_trade(ts, "OPEN", order_price, size_per_trade, fee_rate)
                    pos.update_liquidation_price(portfolio.capital)
                    position = pos
                    active_order = {
                        "price": position.take_profit_price,
                        "side": "SELL",
                        "is_tp": True,
                    }
                else:
                    active_order = {
                        "price": order_price,
                        "side": "LONG",
                        "is_tp": False,
                        "stale_count": 0,
                    }
            portfolio.update_equity(ts)

        elif signal_short[i] and not position:
            if active_order and not active_order.get("is_tp"):
                pass
            else:
                order_price = maker_price(price, "SHORT", offset_pct)
                if h >= order_price:
                    pos = Position(symbol, "SHORT", size_per_trade, position_cfg)
                    pos.entry_score = entry_score_short[i]
                    pos.add_trade(ts, "OPEN", order_price, size_per_trade, fee_rate)
                    pos.update_liquidation_price(portfolio.capital)
                    position = pos
                    active_order = {
                        "price": position.take_profit_price,
                        "side": "BUY",
                        "is_tp": True,
                    }
                else:
                    active_order = {
                        "price": order_price,
                        "side": "SHORT",
                        "is_tp": False,
                        "stale_count": 0,
                    }
            portfolio.update_equity(ts)

        else:
            # ไม่มีสัญญาณใหม่ → ถ้ามี pending order รองาน → นับอายุ
            if active_order and not active_order.get("is_tp"):
                active_order["stale_count"] = active_order.get("stale_count", 0) + 1
                # ถ้าเกิน 10 นาที → ยกเลิก order
                if active_order["stale_count"] >= 10:
                    active_order = None
            else:
                active_order = None
            portfolio.update_equity(ts)

        pbar.update(1)

    pbar.close()

    # ====== Close open position at end ======
    if position is not None and position.status == "OPEN":
        last_ts = timestamps[-1]
        last_price = closes[-1]
        position.close(last_ts, last_price, fee_rate)
        pnl = position.pnl(last_price)
        portfolio.record_trade(TradeLog(
            symbol=symbol, side=position.side,
            open_time=position.records[0].timestamp, close_time=last_ts,
            ep=position.entry_price, bep=position.bep,
            tp=position.take_profit_price, dca_count=position.dca_count,
            pnl_usd=round(pnl, 2),
            pnl_pct=round(pnl / position.total_size_usd * 100, 4),
            fee_usd=round(position.total_fees_usd, 2),
            holding_minutes=position.holding_time_minutes,
            max_distance_pct=round(position.max_distance_pct, 4),
            entry_score=round(position.entry_score, 2),
                    close_reason="END",
        ))
        portfolio.update_equity(last_ts)

    # ====== Build results ======
    trades_df = portfolio.trades_to_dataframe()
    equity_curve = pd.DataFrame(portfolio.equity_curve)
    stats = portfolio.get_stats()

    result = {
        "stats": stats,
        "equity_curve": equity_curve,
        "trades": trades_df,
    }

    # ====== Auto-save results ======
    _auto_save_results(symbol, result, cfg)

    return result
