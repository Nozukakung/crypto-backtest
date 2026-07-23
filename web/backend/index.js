const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const csv = require('csv-parser');

const app = express();
const PORT = process.env.PORT || 5001;
const RESULTS_DIR = path.join(__dirname, '../../results');

app.use(cors());
app.use(express.json());

// 1. ดึงรายการ Runs ทั้งหมด (เรียงตามใหม่สุด)
app.get('/api/runs', (req, res) => {
  try {
    if (!fs.existsSync(RESULTS_DIR)) {
      return res.json([]);
    }

    const files = fs.readdirSync(RESULTS_DIR);
    const runs = [];

    files.forEach(file => {
      const fullPath = path.join(RESULTS_DIR, file);
      const stat = fs.statSync(fullPath);

      if (stat.isDirectory() && file !== 'latest' && file !== 'configs') {
        const summaryPath = path.join(fullPath, 'summary.json');
        let summary = null;
        
        if (fs.existsSync(summaryPath)) {
          summary = JSON.parse(fs.readFileSync(summaryPath, 'utf8'));
        }

        runs.push({
          id: file,
          time: file.replace('_', ' '),
          summary: summary
        });
      }
    });

    // เรียง timestamp ล่าสุดขึ้นก่อน
    runs.sort((a, b) => b.id.localeCompare(a.id));
    res.json(runs);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// 2. ดึง stats รายเหรียญ (ใช้ตอนเปลี่ยน Symbol)
app.get('/api/runs/:id/stats/:symbol', (req, res) => {
  const { id, symbol } = req.params;
  const statsPath = path.join(RESULTS_DIR, id, `${symbol}_stats.json`);

  if (!fs.existsSync(statsPath)) {
    return res.status(404).json({ error: `Stats for ${symbol} not found in run ${id}` });
  }

  try {
    const stats = JSON.parse(fs.readFileSync(statsPath, 'utf8'));
    res.json(stats);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// 3. ดึง summary ของ Run (ใช้ครั้งแรก)
app.get('/api/runs/:id', (req, res) => {
  const { id } = req.params;
  const runPath = path.join(RESULTS_DIR, id);

  if (!fs.existsSync(runPath)) {
    return res.status(404).json({ error: 'Run not found' });
  }

  try {
    // ลองหา BTCUSDT_stats.json ก่อน (fallback)
    const btcPath = path.join(runPath, 'BTCUSDT_stats.json');
    if (fs.existsSync(btcPath)) {
      return res.json(JSON.parse(fs.readFileSync(btcPath, 'utf8')));
    }
    // fallback ไป summary.json
    const summaryPath = path.join(runPath, 'summary.json');
    if (!fs.existsSync(summaryPath)) {
      return res.status(404).json({ error: 'Summary data not found' });
    }
    res.json(JSON.parse(fs.readFileSync(summaryPath, 'utf8')));
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// 4. ดึง CSV Trades ของเหรียญใน Run นั้นๆ
app.get('/api/runs/:id/trades/:symbol', (req, res) => {
  const { id, symbol } = req.params;
  const csvPath = path.join(RESULTS_DIR, id, `${symbol}_trades.csv`);

  if (!fs.existsSync(csvPath)) {
    return res.status(404).json({ error: `Trades CSV for ${symbol} not found` });
  }

  const results = [];
  fs.createReadStream(csvPath)
    .pipe(csv())
    .on('data', (data) => results.push(data))
    .on('end', () => {
      res.json(results);
    })
    .on('error', (err) => {
      res.status(500).json({ error: err.message });
    });
});

app.listen(PORT, () => {
  console.log(`🚀 Backend server is running on port ${PORT}`);
});
