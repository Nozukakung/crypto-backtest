# 📈 Crypto Backtest System — Mean Reversion + DCA (RSI Signal)

ระบบ Backtest สำหรับทดสอบกลยุทธ์เทรด Crypto Futures แบบ Mean Reversion + DCA โดยใช้ RSI เป็น Signal หลัก

## ที่มาของกลยุทธ์

กลยุทธ์นี้ถอดแบบมาจาก "ตาเล็ก วินโด้เก้าแปดเอสอี" (Facebook: windows98SE) — โปรแกรมเมอร์/เทรดเดอร์ Crypto Futures ที่เปิดเผยเทคนิคบอทเทรดของตัวเอง และโพสต์ PnL จริงต่อเนื่องกว่า 2 ปี

**อ่านเอกสารวิเคราะห์กลยุทธ์ฉบับเต็ม:** [docs/STRATEGY_ANALYSIS.md](docs/STRATEGY_ANALYSIS.md)

## กลยุทธ์หลัก

| ค่า | รายละเอียด |
|-----|-----------|
| **Timeframe** | 1 นาที (TF 1m) |
| **Signal** | RSI(14) + Candle Pattern |
| **Order Type** | Maker limit order ทุกไม้ |
| **Take Profit** | BEP + 0.2% |
| **DCA Trigger** | ราคาต่ำกว่า BEP 0.3% |
| **Max Position** | $50,000/คู่ |

## การติดตั้ง

```bash
# Clone repo
git clone https://github.com/Nozukakung/crypto-backtest.git
cd crypto-backtest

# สร้าง virtual environment
python3 -m venv .venv
source .venv/bin/activate

# ติดตั้ง dependencies
pip install -r requirements.txt
```

## โครงสร้างโปรเจกต์

```
crypto-backtest/
├── data/              # ดึงและจัดการข้อมูล OHLC
├── engine/            # Signal, Order, Position Manager
├── backtest/          # ตัวรัน Backtest หลัก
├── analytics/         # คำนวณสถิติและสร้างรายงาน
├── config/            # พารามิเตอร์กลยุทธ์
├── docs/              # เอกสารวิเคราะห์และแผนพัฒนา
├── tests/             # Unit Tests
├── main.py            # จุดเริ่มต้น
└── requirements.txt
```

## วิธีใช้งาน

```bash
# 1. ดาวน์โหลดข้อมูล OHLC 1m
python main.py fetch --symbol BTCUSDT --start 2023-01-01 --end 2026-01-01

# 2. รัน Backtest
python main.py backtest --symbol BTCUSDT --config config/strategy.yaml

# 3. สร้างรายงาน
python main.py report --output reports/
```

## Roadmap

| Phase | สถานะ | รายละเอียด |
|-------|-------|-----------|
| Phase 1 | 🔴 ยังไม่เริ่ม | Data Pipeline — ดาวน์โหลด OHLC 1m |
| Phase 2 | 🔴 ยังไม่เริ่ม | Signal Engine — RSI + Pattern |
| Phase 3 | 🔴 ยังไม่เริ่ม | Order + Position Manager |
| Phase 4 | 🔴 ยังไม่เริ่ม | Backtest Runner |
| Phase 5 | 🔴 ยังไม่เริ่ม | Analytics + Report |
| Phase 6 | 🔴 ยังไม่เริ่ม | ตรวจสอบและปรับปรุง |

**แผนพัฒนาเต็ม:** [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)

## License

MIT License

## หมายเหตุ

- ⚠️ ไม่ได้เชิญชวนเทรด ไม่ได้แจก ไม่ได้สอน
- ข้อมูลจากโพสต์สาธารณะของ "ตาเล็ก วินโด้เก้าแปดเอสอี"
- ใช้สำหรับการศึกษาและวิจัยเท่านั้น