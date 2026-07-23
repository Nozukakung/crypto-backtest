const express = require('express');
const cors = require('cors');
const path = require('path');
const sqlite3 = require('sqlite3').verbose();

const app = express();
const PORT = process.env.PORT || 5001;
const DB_PATH = path.join(__dirname, '../../results/backtest.db');

app.use(cors());
app.use(express.json());

// เปิด connection SQLite
let db;
function openDb() {
  if (!db) {
    db = new sqlite3.Database(DB_PATH, (err) => {
      if (err) console.error('❌ SQLite connection error:', err.message);
      else console.log('✅ Connected to SQLite DB:', DB_PATH);
    });
    db.run("PRAGMA journal_mode = WAL"); // เพิ่มความเร็ว concurrent read
    db.run("PRAGMA cache_size = -10000"); // 10MB cache
  }
  return db;
}

// Helper: ดึง run_timestamp ล่าสุดหรือ run_timestamp ตาม id
function getRunTimestamp(id, cb) {
  const ddb = openDb();
  if (id === 'latest') {
    ddb.get("SELECT run_timestamp FROM runs ORDER BY run_timestamp DESC LIMIT 1", (err, row) => {
      if (err || !row) cb(null);
      else cb(row.run_timestamp);
    });
  } else {
    cb(id);
  }
}

// 1. ดึงรายการ Runs ทั้งหมด
app.get('/api/runs', (req, res) => {
  openDb().all(
    `SELECT run_timestamp as id, run_timestamp as time, 
            total_pnl_usd, max_drawdown_pct, total_trades, 
            total_liquidations, max_dca_any_symbol, config_hash
     FROM runs ORDER BY run_timestamp DESC`, 
    (err, rows) => {
      if (err) return res.status(500).json({ error: err.message });
      const runs = rows.map(r => ({ ...r, summary: null }));
      res.json(runs);
    }
  );
});

// 2. ดึง stats รายเหรียญ
app.get('/api/runs/:id/stats/:symbol', (req, res) => {
  const { id, symbol } = req.params;
  
  getRunTimestamp(id, (runTimestamp) => {
    if (!runTimestamp) return res.status(404).json({ error: 'No run found' });
    
    openDb().get(
      `SELECT 
          r.run_timestamp as run_at,
          r.config_hash,
          SUM(t.pnl_usd) as total_pnl_usd,
          MAX(t.pnl_usd) as max_drawdown_pct,
          SUM(CASE WHEN t.close_reason != 'LIQUIDATE' THEN 1 ELSE 0 END) as winning_trades,
          COUNT(*) as total_trades,
          SUM(CASE WHEN t.close_reason = 'LIQUIDATE' THEN 1 ELSE 0 END) as liquidations,
          MAX(t.dca_count) as max_dca_count,
          AVG(t.dca_count) as avg_dca_count,
          MAX(t.holding_minutes) as max_holding_minutes,
          AVG(t.holding_minutes) as avg_holding_minutes,
          SUM(CASE WHEN t.close_reason = 'TP' THEN 1 ELSE 0 END) as tp_count,
          SUM(CASE WHEN t.close_reason = 'END' THEN 1 ELSE 0 END) as end_count,
          SUM(CASE WHEN t.side = 'LONG' THEN 1 ELSE 0 END) as long_count,
          SUM(CASE WHEN t.side = 'SHORT' THEN 1 ELSE 0 END) as short_count,
          SUM(CASE WHEN t.side = 'LONG' THEN t.pnl_usd ELSE 0 END) as long_pnl,
          SUM(CASE WHEN t.side = 'SHORT' THEN t.pnl_usd ELSE 0 END) as short_pnl,
          MAX(CASE WHEN t.side = 'LONG' THEN t.dca_count ELSE 0 END) as long_max_dca,
          MAX(CASE WHEN t.side = 'SHORT' THEN t.dca_count ELSE 0 END) as short_max_dca,
          MAX(t.max_distance_pct) as max_distance_pct,
          AVG(t.max_distance_pct) as avg_distance_pct
       FROM runs r
       INNER JOIN trades t ON t.run_id = r.id
       WHERE r.run_timestamp = ? AND t.symbol = ?
       GROUP BY r.id`,
      [runTimestamp, symbol],
      (err, row) => {
        if (err) return res.status(500).json({ error: err.message });
        if (!row || row.total_trades === 0) return res.status(404).json({ error: 'No data' });

        const wr = (row.winning_trades / row.total_trades * 100) || 0;
        res.json({
          symbol,
          run_at: row.run_at,
          config_hash: parseInt(row.config_hash, 16) || 0,
          stats: {
            total_pnl_usd: row.total_pnl_usd || 0,
            max_drawdown_pct: row.max_drawdown_pct || 0,
            win_rate: wr,
            total_trades: row.total_trades
          },
          trades_summary: {
            max_dca_count: row.max_dca_count || 0,
            avg_dca_count: row.avg_dca_count || 0,
            median_dca_count: 0,
            max_holding_minutes: row.max_holding_minutes || 0,
            avg_holding_minutes: row.avg_holding_minutes || 0,
            liquidations: row.liquidations || 0,
            tp_count: row.tp_count || 0,
            end_count: row.end_count || 0
          },
          margin_analysis: {
            max_margin_used_usd: ((row.max_dca_count || 0) + 1) * 200 / 10,
            free_margin_remaining: 50000 - ((row.max_dca_count || 0) + 1) * 200 / 10
          },
          side_breakdown: {
            long: { count: row.long_count, pnl: row.long_pnl, max_dca: row.long_max_dca },
            short: { count: row.short_count, pnl: row.short_pnl, max_dca: row.short_max_dca }
          },
          distance_analysis: {
            max_distance_pct: row.max_distance_pct || 0,
            avg_distance_pct: row.avg_distance_pct || 0
          }
        });
      }
    );
  });
});

// 3. ดึง Trades แบบ Pagination + Sorting จาก DB
app.get('/api/runs/:id/trades/:symbol', (req, res) => {
  const { id, symbol } = req.params;
  const page = parseInt(req.query.page) || 1;
  const limit = parseInt(req.query.limit) || 50;
  const sort = req.query.sort || 'holding_minutes';
  const order = req.query.order === 'asc' ? 'ASC' : 'DESC';

  const sortCols = {
    'index': 't.id', 'side': 't.side', 'open_time': 't.open_time',
    'ep': 't.ep', 'dca_count': 't.dca_count', 'pnl_usd': 't.pnl_usd',
    'holding_minutes': 't.holding_minutes', 'close_reason': 't.close_reason',
    'max_distance_pct': 't.max_distance_pct'
  };
  const sortCol = sortCols[sort] || 't.open_time';

  const ddb = openDb();
  
  getRunTimestamp(id, (runTimestamp) => {
    if (!runTimestamp) return res.status(404).json({ error: 'No run found' });

    ddb.get(
      `SELECT COUNT(*) as total FROM trades t 
       INNER JOIN runs r ON t.run_id = r.id
       WHERE r.run_timestamp = ? AND t.symbol = ?`,
      [runTimestamp, symbol],
      (err, countRow) => {
        if (err) return res.status(500).json({ error: err.message });
        
        const total = countRow?.total || 0;
        const offset = (page - 1) * limit;
        
        ddb.all(
          `SELECT t.* FROM trades t
           INNER JOIN runs r ON t.run_id = r.id
           WHERE r.run_timestamp = ? AND t.symbol = ?
           ORDER BY ${sortCol} ${order}
           LIMIT ? OFFSET ?`,
          [runTimestamp, symbol, limit, offset],
          (err2, rows) => {
            if (err2) return res.status(500).json({ error: err2.message });
            res.json({
              trades: rows,
              total,
              page,
              limit,
              totalPages: Math.ceil(total / limit)
            });
          }
        );
      }
    );
  });
});

// 4. Fallback
app.get('/api/runs/:id', (req, res) => {
  const { id } = req.params;
  
  getRunTimestamp(id, (runTimestamp) => {
    if (!runTimestamp) return res.status(404).json({ error: 'Run not found' });
    
    openDb().get(
      `SELECT * FROM runs WHERE run_timestamp = ?`,
      [runTimestamp],
      (err, row) => {
        if (err || !row) return res.status(404).json({ error: 'Run not found' });
        res.json({
          symbol: 'BTCUSDT',
          run_at: row.run_timestamp,
          stats: { total_pnl_usd: row.total_pnl_usd, max_drawdown_pct: row.max_drawdown_pct, total_trades: row.total_trades, win_rate: 100 },
          trades_summary: { max_dca_count: row.max_dca_any_symbol, liquidations: row.total_liquidations }
        });
      }
    );
  });
});

app.listen(PORT, () => console.log(`🚀 Backend API on port ${PORT} (SQLite)`));
