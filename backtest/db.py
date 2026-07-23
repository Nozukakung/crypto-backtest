"""
Database module for Crypto Backtest results
SQLite storage for trades and run stats
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import hashlib

DB_PATH = Path("results/backtest.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp TEXT NOT NULL UNIQUE,
    run_name TEXT NOT NULL,
    config_hash TEXT,
    total_pnl_usd REAL,
    max_drawdown_pct REAL,
    total_trades INTEGER,
    total_liquidations INTEGER,
    max_dca_any_symbol INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    open_time TEXT NOT NULL,
    close_time TEXT,
    ep REAL,
    bep REAL,
    tp REAL,
    dca_count INTEGER DEFAULT 0,
    pnl_usd REAL,
    pnl_pct REAL,
    fee_usd REAL,
    holding_minutes INTEGER,
    close_reason TEXT,
    max_distance_pct REAL DEFAULT 0.0,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_trades_run_symbol ON trades(run_id, symbol);
CREATE INDEX IF NOT EXISTS idx_trades_run_holding ON trades(run_id, holding_minutes);
CREATE INDEX IF NOT EXISTS idx_trades_run_pnl ON trades(run_id, pnl_usd);
CREATE INDEX IF NOT EXISTS idx_trades_run_dca ON trades(run_id, dca_count);
"""

def get_conn():
    """Get database connection with row factory"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database schema"""
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

def save_run(symbols: List[str], results: Dict[str, Any], cfg: Dict, timestamp: str):
    """Save a full backtest run to database"""
    conn = get_conn()
    cursor = conn.cursor()
    
    # Compute config hash
    config_hash = hashlib.md5(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]
    
    # Calculate aggregate stats
    all_trades = []
    total_pnl = 0
    max_dd = 0
    total_trades = 0
    total_liq = 0
    max_dca = 0
    
    for sym in symbols:
        trades = results[sym].get('trades', [])
        stats = results[sym].get('stats', {})
        total_pnl += stats.get('total_pnl_usd', 0)
        max_dd = max(max_dd, stats.get('max_drawdown_pct', 0))
        total_trades += len(trades)
        total_liq += sum(1 for t in trades if t.get('close_reason') == 'LIQUIDATE')
        if trades:
            max_dca = max(max_dca, max(t.get('dca_count', 0) for t in trades))
        all_trades.extend(trades)
    
    # Insert run
    cursor.execute("""
        INSERT OR REPLACE INTO runs (run_timestamp, run_name, config_hash, total_pnl_usd, max_drawdown_pct, total_trades, total_liquidations, max_dca_any_symbol)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, timestamp.replace('_', ' '), config_hash, total_pnl, max_dd, total_trades, total_liq, max_dca))
    
    run_id = cursor.lastrowid
    
    # Insert trades
    for t in all_trades:
        cursor.execute("""
            INSERT INTO trades (run_id, symbol, side, open_time, close_time, ep, bep, tp, dca_count, pnl_usd, pnl_pct, fee_usd, holding_minutes, close_reason, max_distance_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            t.get('symbol'),
            t.get('side'),
            t.get('open_time'),
            t.get('close_time'),
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
        ))
    
    conn.commit()
    conn.close()
    return run_id

def get_runs() -> List[Dict]:
    """Get all runs ordered by timestamp desc"""
    conn = get_conn()
    cursor = conn.execute("""
        SELECT id, run_timestamp as id, run_timestamp as time, 
               total_pnl_usd, max_drawdown_pct, total_trades, total_liquidations, max_dca_any_symbol,
               config_hash
        FROM runs ORDER BY run_timestamp DESC
    """)
    runs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return runs

def get_run_stats(run_id: int, symbol: str) -> Optional[Dict]:
    """Get stats for a specific symbol in a run"""
    conn = get_conn()
    cursor = conn.execute("""
        SELECT 
            r.id, r.run_timestamp, r.config_hash,
            SUM(CASE WHEN t.symbol = ? THEN t.pnl_usd ELSE 0 END) as total_pnl_usd,
            MAX(CASE WHEN t.symbol = ? THEN t.pnl_usd ELSE 0 END) as max_drawdown_pct,
            SUM(CASE WHEN t.symbol = ? AND t.close_reason != 'LIQUIDATE' THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN t.symbol = ? THEN 1 ELSE 0 END) as total_trades,
            SUM(CASE WHEN t.symbol = ? AND t.close_reason = 'LIQUIDATE' THEN 1 ELSE 0 END) as liquidations,
            MAX(CASE WHEN t.symbol = ? THEN t.dca_count ELSE 0 END) as max_dca_count,
            AVG(CASE WHEN t.symbol = ? THEN t.dca_count ELSE 0 END) as avg_dca_count,
            MAX(CASE WHEN t.symbol = ? THEN t.holding_minutes ELSE 0 END) as max_holding_minutes,
            AVG(CASE WHEN t.symbol = ? THEN t.holding_minutes ELSE 0 END) as avg_holding_minutes,
            SUM(CASE WHEN t.symbol = ? AND t.close_reason = 'TP' THEN 1 ELSE 0 END) as tp_count,
            SUM(CASE WHEN t.symbol = ? AND t.close_reason = 'END' THEN 1 ELSE 0 END) as end_count,
            SUM(CASE WHEN t.symbol = ? AND t.side = 'LONG' THEN 1 ELSE 0 END) as long_count,
            SUM(CASE WHEN t.symbol = ? AND t.side = 'SHORT' THEN 1 ELSE 0 END) as short_count,
            SUM(CASE WHEN t.symbol = ? AND t.side = 'LONG' THEN t.pnl_usd ELSE 0 END) as long_pnl,
            SUM(CASE WHEN t.symbol = ? AND t.side = 'SHORT' THEN t.pnl_usd ELSE 0 END) as short_pnl,
            MAX(CASE WHEN t.symbol = ? AND t.side = 'LONG' THEN t.dca_count ELSE 0 END) as long_max_dca,
            MAX(CASE WHEN t.symbol = ? AND t.side = 'SHORT' THEN t.dca_count ELSE 0 END) as short_max_dca
        FROM runs r
        LEFT JOIN trades t ON t.run_id = r.id
        WHERE r.id = ?
        GROUP BY r.id
    """, [symbol]*21 + [run_id])
    
    row = cursor.fetchone()
    conn.close()
    
    if not row or row['total_trades'] == 0:
        return None
    
    d = dict(row)
    # Calculate win rate
    wr = (d['winning_trades'] / d['total_trades'] * 100) if d['total_trades'] > 0 else 0
    
    return {
        "symbol": symbol,
        "run_at": d['run_timestamp'],
        "config_hash": int(d['config_hash'], 16) if d['config_hash'] else 0,
        "stats": {
            "total_pnl_usd": d['total_pnl_usd'] or 0,
            "max_drawdown_pct": d['max_drawdown_pct'] or 0,
            "win_rate": wr,
            "total_trades": d['total_trades'] or 0,
        },
        "trades_summary": {
            "max_dca_count": d['max_dca_count'] or 0,
            "avg_dca_count": d['avg_dca_count'] or 0,
            "median_dca_count": 0,  # SQLite doesn't have median
            "max_holding_minutes": d['max_holding_minutes'] or 0,
            "avg_holding_minutes": d['avg_holding_minutes'] or 0,
            "liquidations": d['liquidations'] or 0,
            "tp_count": d['tp_count'] or 0,
            "end_count": d['end_count'] or 0,
        },
        "margin_analysis": {
            "max_margin_used_usd": ((d['max_dca_count'] or 0) + 1) * 200 / 10,
            "free_margin_remaining": 50000 - ((d['max_dca_count'] or 0) + 1) * 200 / 10,
        },
        "side_breakdown": {
            "long": {
                "count": d['long_count'] or 0,
                "pnl": d['long_pnl'] or 0,
                "max_dca": d['long_max_dca'] or 0,
            },
            "short": {
                "count": d['short_count'] or 0,
                "pnl": d['short_pnl'] or 0,
                "max_dca": d['short_max_dca'] or 0,
            }
        }
    }

def get_trades(run_id: int, symbol: str, page: int = 1, limit: int = 50, sort: str = 'open_time', order: str = 'desc') -> Dict:
    """Get paginated trades for a symbol in a run"""
    conn = get_conn()
    
    # Valid sort columns
    sort_cols = {
        'index': 't.id',
        'side': 't.side',
        'open_time': 't.open_time',
        'ep': 't.ep',
        'dca_count': 't.dca_count',
        'pnl_usd': 't.pnl_usd',
        'holding_minutes': 't.holding_minutes',
        'close_reason': 't.close_reason',
        'max_distance_pct': 't.max_distance_pct'
    }
    
    sort_col = sort_cols.get(sort, 't.open_time')
    order_dir = 'ASC' if order == 'asc' else 'DESC'
    
    # Get total count
    total = conn.execute("SELECT COUNT(*) FROM trades WHERE run_id = ? AND symbol = ?", (run_id, symbol)).fetchone()[0]
    
    # Get paginated trades
    offset = (page - 1) * limit
    cursor = conn.execute(f"""
        SELECT 
            t.id, t.symbol, t.side, t.open_time, t.close_time, t.ep, t.bep, t.tp,
            t.dca_count, t.pnl_usd, t.pnl_pct, t.fee_usd, t.holding_minutes, t.close_reason, t.max_distance_pct
        FROM trades t
        WHERE t.run_id = ? AND t.symbol = ?
        ORDER BY {sort_col} {order_dir}
        LIMIT ? OFFSET ?
    """, (run_id, symbol, limit, offset))
    
    trades = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {
        "trades": trades,
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": (total + limit - 1) // limit
    }

# Initialize on import
init_db()

if __name__ == "__main__":
    # Test
    print("Database initialized at", DB_PATH)
    runs = get_runs()
    print(f"Total runs: {len(runs)}")
    for r in runs[:3]:
        print(f"  {r['id']}: {r['time']} PnL={r['total_pnl_usd']} Trades={r['total_trades']}")