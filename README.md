# 📈 Crypto Backtest — Mean Reversion + DCA (ตาเล็ก 98SE)

ระบบ Backtest สำหรับทดสอบกลยุทธ์เทรด Crypto Futures แบบ Mean Reversion + DCA ด้วย RSI Signal

> กลยุทธ์ถอดแบบมาจาก "ตาเล็ก วินโด้เก้าแปดเอสอี" (Facebook: windows98SE) — PnL จริง 2+ ปี

## 📊 ผลลัพธ์ล่าสุด (Config: Cap $50K, No Timeout, TP 0.2%, No CutLoss, 10x)

| เหรียญ | PnL | DD | Max DCA | Liq | Trades | WR |
|:------:|:---:|:--:|:-------:|:---:|:------:|:--:|
| **BTC** | **+$3,707** 🔥 | **0.00%** | 277 | 0 | 2,462 | 100% |
| **DOGE** | **+$13,761** 🔥 | **0.00%** | 252 | 0 | 10,959 | 100% |
| **BNB** | **+$6,393** 🔥 | **0.00%** | 253 | 0 | 4,516 | 100% |
| **ETH** | **+$4,413** | 8.73% | 253 | 1 | 6,226 | 100% |
| **TOTAL** | **+$28,274** 🔥🔥 | **8.73%** | **277** | **1** | **24,163** | **100%** |

> ROI 56.5% ใน 3 ปี (~18.8%/ปี) • DD 8.73% • Max DCA 277 ไม้ • Liq 1 ครั้ง (ETH)

## ⚙️ Config (ตาเล็กต้นฉบับ)

```yaml
leverage: 10x
size_per_trade_usd: 200
order:
  type: Maker (Limit)
  price_offset_percent: 0.05
  take_profit_above_bep_percent: 0.2

position:
  dca_trigger_below_bep_percent: 0.3   # DCA Grid: ห่างจาก BEP > 0.3%
  dca_multiplier: 1.0                   # Grid คงที่
  dca_max_cap_usd: 50000.0             # Cap $50K (margin $5K)
  long_timeout_minutes: 9999999         # ไม่มี Timeout (ตาเล็กจริง)
  short_timeout_minutes: 9999999
  cutloss_after_stop_minutes: 9999999   # ไม่มี CutLoss

signal:
  mode: rsi_only
  rsi_period: 14
  rsi_long: 40
  rsi_short: 60

portfolio:
  initial_capital: 50000.0
  margin_mode: cross
  liquidation_buffer_percent: 0.50     # ยอมติดลบ 50% ก่อน Liq
```

## 🏗️ โครงสร้างโปรเจกต์

```
crypto-backtest/
├── data/
│   ├── store.py          # CSV → Parquet + Validate + Fill Gaps
│   └── parquet/          # ข้อมูล OHLC 1m (per symbol)
├── engine/
│   ├── indicators.py     # RSI(14) Wilder's + Candle Features
│   ├── exchange.py       # Lot/Tick Size, round_price
│   └── position.py       # Position + DCA + TP + BEP + Liquidation
├── backtest/
│   ├── runner.py         # Main Loop (signal calc inline)
│   └── portfolio.py      # Equity + Trade Log + Drawdown
├── analytics/
│   └── report.py         # HTML Report (Chart.js)
├── config/
│   └── strategy.yaml     # พารามิเตอร์ทั้งหมด
├── results/              # ผลลัพธ์ Backtest (JSON + CSV)
├── main.py
├── save_results.py       # บันทึกผลลัพธ์ Backtest
├── query_results.py      # วิเคราะห์ผลลัพธ์จากที่บันทึกไว้
├── stats.py              # สถิติรายวัน/สัปดาห์/เดือน
└── Note.md               # บันทึกกลยุทธ์และบทเรียน
```

## 🚀 วิธีใช้งาน

```bash
# Clone
git clone https://github.com/Nozukakung/crypto-backtest.git
cd crypto-backtest

# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# รัน Backtest 4 เหรียญ
python -c "
from backtest.runner import run_backtest, load_config
cfg = load_config()
for sym in ['BTCUSDT','DOGEUSDT','BNBUSDT','ETHUSDT']:
    r = run_backtest(sym, cfg)
    s = r['stats']; df = r['trades']
    print(f\"{sym}: PnL \${s['total_pnl_usd']:>8,.2f} | DD {s['max_drawdown_pct']:.2f}% | Max DCA {int(df['dca_count'].max())} | Liq {(df['close_reason']=='LIQUIDATE').sum()} | Trades {len(df)}\")
"

# บันทึกผลลัพธ์ (ไม่ต้องรันใหม่!)
python save_results.py

# ดูผลลัพธ์ที่บันทึกไว้ (เร็วมาก)
python query_results.py              # สรุปรวม
python query_results.py BTCUSDT      # เจาะลึก BTC
```

## 🔑 กฎเหล็กของกลยุทธ์

### 1. DCA Grid — เช็คห่างจาก BEP > 0.3%
```python
# LONG: ต้องต่ำกว่า BEP > 0.3% ถึงจะ DCA
pct_under = (BEP - current_price) / BEP
if pct_under > 0.003:
    dca_count += 1
```

### 2. Cap $50K — จำกัด Margin สูงสุด
- Max DCA = $50,000 / $200 × 10x leverage = **250 ไม้**
- Margin สูงสุด = **$5,500** (จาก Capital $50K)

### 3. TP = BEP + 0.2% — รอราคากลับมา TP เสมอ
- **ห้าม CutLoss** — ถือค้างรอ Mean Reversion
- ตาเล็กจริงไม่มี Timeout (ไม่มีมัดรวม) → ถัวจนกว่าจะชน Cap

### 4. Cross Margin — Buffer 50% ค้ำพอร์ต
```
Buffer Fund = $50,000 × 50% = $25,000
→ ต้องขาดทุนเกิน $25,000 ถึงจะ Liq
→ Liq Distance = Entry ± 53%
```

## 🐛 Bug Fixes (สำคัญ!)

| # | Bug | Fix |
|---|-----|-----|
| 1 | Liq Price คำนวณผิด (Isolated Margin fallback) | ส่ง `portfolio.capital` เสมอ + Cross Margin Buffer 50% |
| 2 | DCA Loop (BEP + ไม่มี Cap/Timeout) → 2,758 ไม้ | ใส่ Cap $50K |
| 3 | Pending Order ถูกสัญญาณทับ | ตรวจสอบ `active_order` ก่อนสร้างใหม่ |
| 4 | Pending Order ไม่มีวันหมดอายุ | Stale Timeout 10 นาที |
| 5 | No Signal → ลบ Pending Order | ตรวจสอบก่อนลบ |
| 6 | Order Loop ไม่มี `continue` | เพิ่ม continue หลัง Order Loop |

ดูรายละเอียดทั้งหมดใน [Note.md](Note.md)

## 📁 Results (บันทึกผลลัพธ์ไว้แล้ว!)

```bash
python query_results.py              # ดูสรุปรวม
python query_results.py BTCUSDT      # เจาะลึก BTC
```

ไฟล์ที่บันทึกไว้:
- `results/summary.json` — สรุปผลทั้งหมด
- `results/*_stats.json` — รายละเอียดรายเหรียญ
- `results/*_trades.csv` — ประวัติเทรดทั้งหมด

## 📄 เอกสารเพิ่มเติม

- [Note.md](Note.md) — บันทึกกลยุทธ์ บทเรียน และสูตรคำนวณ
- [docs/STRATEGY_ANALYSIS.md](docs/STRATEGY_ANALYSIS.md) — วิเคราะห์กลยุทธ์ฉบับเต็ม

## ⚠️ หมายเหตุ

- ไม่ได้เชิญชวนเทรด • ไม่ได้แจก • ไม่ได้สอน
- ใช้สำหรับการศึกษาและวิจัยเท่านั้น
- Backtest ≠ กำไรจริง (~85-95% ของ Backtest)

## License

MIT License
