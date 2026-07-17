"""
data/store.py — โหลด CSV OHLC 1m → Parquet + Validate
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime


DATA_DIR = Path(__file__).parent.parent / "data" / "parquet"


def load_csv(path: str | Path) -> pd.DataFrame:
    """โหลด CSV แล้ว convert เป็น DataFrame ที่พร้อมใช้"""
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    # ตรวจสอบคอลัมน์
    expected = ["timestamp", "open", "high", "low", "close", "volume"]
    for col in expected:
        assert col in df.columns, f"Missing column: {col}"

    # ตรวจสอบค่า
    assert df["open"].gt(0).all(), "Found zero/negative open"
    assert df["high"].ge(df["open"]).all(), "high < open detected"
    assert df["low"].le(df["open"]).all(), "low > open detected"
    assert df["high"].ge(df["low"]).all(), "high < low detected"
    assert df["close"].gt(0).all(), "Found zero/negative close"

    return df


def validate_klines(df: pd.DataFrame, symbol: str) -> dict:
    """ตรวจสอบความสมบูรณ์ของข้อมูล OHLC"""
    report = {
        "symbol": symbol,
        "total_rows": len(df),
        "start": df["timestamp"].min().isoformat(),
        "end": df["timestamp"].max().isoformat(),
        "missing_gaps": 0,
        "duplicated_timestamps": 0,
        "zero_volume_rows": 0,
        "status": "OK",
    }

    # เช็ค duplicated
    dupes = df["timestamp"].duplicated().sum()
    report["duplicated_timestamps"] = int(dupes)

    # เช็คช่องว่าง (gaps มากกว่า 2 นาที)
    if len(df) > 1:
        diffs = df["timestamp"].diff().dt.total_seconds()
        gaps = (diffs > 120).sum()  # มากกว่า 2 นาที = มีช่องว่าง
        report["missing_gaps"] = int(gaps)

    # เช็ค volume = 0
    report["zero_volume_rows"] = int((df["volume"] == 0).sum())

    if dupes > 0 or report["missing_gaps"] > 0:
        report["status"] = "WARN"

    return report


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """ลบ duplicate timestamp (เอาตัวหลัง)"""
    return df.drop_duplicates(subset="timestamp", keep="last").reset_index(drop=True)


def fill_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """เติมช่องว่าง的时间戳 ด้วย forward-fill"""
    full_idx = pd.date_range(
        start=df["timestamp"].min(),
        end=df["timestamp"].max(),
        freq="1min",
        tz="UTC",
    )
    df = df.set_index("timestamp").reindex(full_idx)
    df.index.name = "timestamp"

    # Forward fill ราคา (ใช้ราคาล่าสุด)
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].ffill()
    df["volume"] = df["volume"].fillna(0)

    df = df.reset_index()
    return df


def to_parquet(df: pd.DataFrame, symbol: str):
    """บันทึกเป็น Parquet"""
    out_dir = DATA_DIR / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "1m.parquet"
    df.to_parquet(out_path, index=False, engine="pyarrow")
    print(f"✅ Saved {len(df)} rows → {out_path}")


def load_parquet(symbol: str) -> pd.DataFrame:
    """โหลด Parquet กลับมา"""
    path = DATA_DIR / symbol / "1m.parquet"
    assert path.exists(), f"Parquet not found: {path}"
    return pd.read_parquet(path, engine="pyarrow")


def process_all(csv_dir: str | Path):
    """ประมวลผล CSV ทั้งหมด → Parquet"""
    csv_dir = Path(csv_dir)
    for csv_file in sorted(csv_dir.glob("*.csv")):
        symbol = csv_file.stem.replace("_1m_data", "")
        print(f"\n{'='*60}")
        print(f"📊 Processing {symbol}...")

        df = load_csv(csv_file)
        report = validate_klines(df, symbol)
        print(f"   Rows: {report['total_rows']:,}")
        print(f"   Period: {report['start']} → {report['end']}")
        print(f"   Gaps: {report['missing_gaps']}, Dupes: {report['duplicated_timestamps']}, ZeroVol: {report['zero_volume_rows']}")

        df = deduplicate(df)
        df = fill_gaps(df)
        to_parquet(df, symbol)
        print(f"   Status: {report['status']}")


if __name__ == "__main__":
    process_all("csv")