# 📝 บันทึกกลยุทธ์ "ตาเล็ก 98SE" — Crypto Backtest

ไฟล์นี้บันทึก **กฎเหล็ก สูตรคำนวณ และบทเรียน** ทั้งหมดจากการพัฒนา

---

## 🎯 1. สรุปผลลัพธ์ล่าสุด

### Config ตัวจบ: Cap $50K, No Timeout, TP 0.2%, No CutLoss, 10x

| เหรียญ | PnL | DD | Max DCA | Liq | Trades | WR |
|:------:|:---:|:--:|:-------:|:---:|:------:|:--:|
| **BTC** | **+$3,707** | **0.00%** | 277 | 0 | 2,462 | 100% |
| **DOGE** | **+$13,761** | **0.00%** | 252 | 0 | 10,959 | 100% |
| **BNB** | **+$6,393** | **0.00%** | 253 | 0 | 4,516 | 100% |
| **ETH** | **+$4,413** | 8.73% | 253 | 1 | 6,226 | 100% |
| **TOTAL** | **+$28,274** | **8.73%** | **277** | **1** | **24,163** | **100%** |

> ROI 56.5% ใน 3 ปี (~18.8%/ปี) • DD 8.73% • Max DCA 277 ไม้ • Liq 1 ครั้ง (ETH)

### Config อื่นๆ ที่ทดสอบ

| Config | PnL | DD | Max DCA | Liq | หมายเหตุ |
|:------:|:---:|:--:|:-------:|:---:|---------|
| Cap $50K, Timeout 30/120 | +$11,360 | 2.53% | 122 | 0 | ปลอดภัยกว่า แต่กำไรน้อยกว่า 2.5x |
| Cap $50K, No Timeout | **+$28,274** 🏆 | 8.73% | 277 | 1 | **ตาเล็กต้นฉบับจริง** |
| No Cap, No Timeout | -$277K | 183% | 2,758 | 2,320 | หายนะ |

---

## 📐 2. กฎและเงื่อนไข

### 2.1 สัญญาณเปิดไม้แรก (Signal — RSI Only)
| ฝั่ง | เงื่อนไข |
|:----:|:--------:|
| **LONG** | RSI(14) < 40 |
| **SHORT** | RSI(14) > 60 |

### 2.2 สัญญาณการถัว (DCA Trigger)
- **ห้ามเช็ค RSI หรือ Candle Pattern ซ้ำ** — สูตรเดิมทำกำไรดีที่สุด
- เช็คห่างจาก **BEP** > 0.3% เท่านั้น:

$$\text{Distance}\% = \frac{|\text{Current Price} - \text{BEP}|}{\text{BEP}} \times 100 \ge 0.3\%$$

### 2.3 Liquidation Price (Cross Margin Buffer 50%)
$$\text{Buffer USD} = \text{Portfolio Capital} \times 0.50$$
- **LONG:** $\text{Liq} = \text{Entry} - \frac{\text{Buffer USD}}{\text{Total QTY}}$
- **SHORT:** $\text{Liq} = \text{Entry} + \frac{\text{Buffer USD}}{\text{Total QTY}}$

### 2.4 TP = BEP + 0.2%
- ห้าม CutLoss เด็ดขาด
- ปล่อย Position ค้างรอ Mean Reversion

### 2.5 Cap $50K
- `total_size_usd >= cap` → หยุดถัว
- Margin สูงสุด = $5,500 (11% ของพอร์ต $50K)
- Free Margin เหลือ = $44,500 (89%)

### 2.6 Timeout (ตาเล็กจริง = ไม่มี!)
- ตาเล็กจริง **ไม่มี Timeout** — ถัวไปเรื่อยๆ จนกว่าจะชน Cap หรือ TP
- ใส่ Timeout 30/120 ไว้เป็นตัวเลือกปลอดภัย

---

## 🐛 3. Bugs ที่แก้แล้ว

| # | Bug | สาเหตุ | Fix |
|---|-----|-------|-----|
| 1 | Liq Price ผิด | ไม่ส่ง `portfolio.capital` → fallback Isolated | ส่ง capital เสมอ + Buffer 50% |
| 2 | DCA Loop无穷 | BEP + ไม่มี Cap → 2,758 ไม้ | ใส่ Cap $50K |
| 3 | Pending Order ถูกทับ | Signal ซ้ำทุกนาทีสร้าง order ใหม่ | เช็ค `active_order` ก่อน |
| 4 | Pending Order ค้างตลอดกาล | ไม่มี Stale Timeout | Stale Timeout 10 นาที |
| 5 | No Signal → ลบ Pending | `else: active_order = None` | ตรวจสอบก่อนลบ |
| 6 | Order Loop ไม่มี continue | ไหลไปโดน signal block | เพิ่ม continue |
| 7 | last_dca_price Grid DCA น้อยไป | Max DCA 10-77 ไม้ | กลับไป BEP-based + ใช้ Cap ป้องกัน |

---

## 💡 4. บทเรียนสำคัญ

1. **DCA Grid ที่ถูกต้อง = BEP-based + Cap + Timeout**
   - BEP-based DCA ถูกต้องแล้ว แต่ต้องมี Cap เป็นขอบเขตเสมอ
   - ไม่ต้องใช้ `last_dca_price` — มันทำให้ Grid ทำงานไม่ถูกต้อง

2. **CutLoss = ทำลาย DCA Mean Reversion**
   - CutLoss ตัดก่อนราคาจะกลับ → ขาดทุนสะสม
   - ใช้ Margin Management (Buffer Fund + Cap) แทน

3. **Cross Margin Buffer 50% ทำให้ DD ต่ำ**
   - Liq Distance = 53% จาก Entry → ถัวลึกได้มาก
   - Max Margin แค่ $5,500 (11% ของพอร์ต)

4. **RSI Only ดีกว่า RSI + Pattern**
   - RSI + Pattern = สัญญาณน้อย 27x → กำไรน้อยกว่า
   - ตาเล็กจริงใช้ RSI Only

5. **Limit Order ต้องดูแลดี**
   - อย่าทับ Pending Order
   - อย่าลบเมื่อไม่มีสัญญาณ
   - ต้องมี Stale Timeout
   - ต้อง `continue` หลัง Order Loop

---

## 📁 5. โครงสร้างไฟล์

```
crypto-backtest/
├── data/store.py          # CSV → Parquet
├── data/parquet/          # ข้อมูล OHLC 1m
├── engine/indicators.py   # RSI(14) Wilder's
├── engine/exchange.py     # Lot/Tick Size
├── engine/position.py     # Position + DCA + TP + Liq
├── backtest/runner.py     # Main Loop
├── backtest/portfolio.py  # Equity + Trade Log
├── analytics/report.py    # HTML Report (Chart.js)
├── config/strategy.yaml   # พารามิเตอร์
├── results/               # ผลลัพธ์ Backtest (JSON + CSV)
├── save_results.py        # บันทึกผลลัพธ์
├── query_results.py       # วิเคราะห์ผลลัพธ์
├── stats.py               # สถิติรายวัน/สัปดาห์/เดือน
├── Note.md                # ไฟล์นี้
└── README.md
```

---

## 🔧 6. Quick Reference

```bash
# รัน Backtest 4 เหรียญ
python -c "
from backtest.runner import run_backtest, load_config
cfg = load_config()
for sym in ['BTCUSDT','DOGEUSDT','BNBUSDT','ETHUSDT']:
    r = run_backtest(sym, cfg)
    s = r['stats']; df = r['trades']
    print(f\"{sym}: PnL \${s['total_pnl_usd']:>8,.2f} | DD {s['max_drawdown_pct']:.2f}% | Max DCA {int(df['dca_count'].max())} | Liq {(df['close_reason']=='LIQUIDATE').sum()} | Trades {len(df)}\")
"

# บันทึกผลลัพธ์
python save_results.py

# ดูผลลัพธ์ที่บันทึกไว้
python query_results.py              # สรุปรวม
python query_results.py BTCUSDT      # เจาะลึก BTC
```

---

*บันทึกโดย Hermes Agent — 22 กรกฎาคม 2026*
