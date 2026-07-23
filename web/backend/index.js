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

// Cache สำหรับ CSV trades
const tradesCache = new Map()

function loadTradesCSV(csvPath) {
  if (tradesCache.has(csvPath)) {
    return Promise.resolve(tradesCache.get(csvPath))
  }
  return new Promise((resolve, reject) => {
    const results = []
    fs.createReadStream(csvPath)
      .pipe(csv())
      .on('data', (data) => results.push(data))
      .on('end', () => {
        tradesCache.set(csvPath, results)
        resolve(results)
      })
      .on('error', reject)
  })
}

// 1. ดึงรายการ Runs ทั้งหมด
app.get('/api/runs', async (req, res) => {
  try {
    if (!fs.existsSync(RESULTS_DIR)) return res.json([])
    const files = fs.readdirSync(RESULTS_DIR)
    const runs = []
    for (const file of files) {
      const fullPath = path.join(RESULTS_DIR, file)
      const stat = fs.statSync(fullPath)
      if (stat.isDirectory() && file !== 'latest' && file !== 'configs') {
        const summaryPath = path.join(fullPath, 'summary.json')
        let summary = null
        if (fs.existsSync(summaryPath)) {
          summary = JSON.parse(fs.readFileSync(summaryPath, 'utf8'))
        }
        runs.push({ id: file, time: file.replace('_', ' '), summary })
      }
    }
    runs.sort((a, b) => b.id.localeCompare(a.id))
    res.json(runs)
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// 2. ดึง stats รายเหรียญ
app.get('/api/runs/:id/stats/:symbol', (req, res) => {
  const { id, symbol } = req.params
  const targetId = id === 'latest' ? 'latest' : id
  const statsPath = path.join(RESULTS_DIR, targetId, `${symbol}_stats.json`)
  if (!fs.existsSync(statsPath)) {
    return res.status(404).json({ error: `Stats for ${symbol} not found` })
  }
  try {
    res.json(JSON.parse(fs.readFileSync(statsPath, 'utf8')))
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// 3. ดึง summary ของ Run
app.get('/api/runs/:id', (req, res) => {
  const { id } = req.params
  const targetId = id === 'latest' ? 'latest' : id
  const runPath = path.join(RESULTS_DIR, targetId)
  if (!fs.existsSync(runPath)) return res.status(404).json({ error: 'Run not found' })
  try {
    const btcPath = path.join(runPath, 'BTCUSDT_stats.json')
    if (fs.existsSync(btcPath)) return res.json(JSON.parse(fs.readFileSync(btcPath, 'utf8')))
    const summaryPath = path.join(runPath, 'summary.json')
    if (!fs.existsSync(summaryPath)) return res.status(404).json({ error: 'Summary not found' })
    res.json(JSON.parse(fs.readFileSync(summaryPath, 'utf8')))
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

// 4. ดึง Trades แบบ Pagination + Server-side Sorting
app.get('/api/runs/:id/trades/:symbol', async (req, res) => {
  try {
    const { id, symbol } = req.params
    const targetId = id === 'latest' ? 'latest' : id
    const csvPath = path.join(RESULTS_DIR, targetId, `${symbol}_trades.csv`)
    if (!fs.existsSync(csvPath)) return res.status(404).json({ error: 'Trades not found' })

    const page = parseInt(req.query.page) || 1
    const limit = parseInt(req.query.limit) || 50
    const sort = req.query.sort || 'holding_minutes'
    const order = req.query.order === 'asc' ? 'asc' : 'desc'

    const allTrades = await loadTradesCSV(csvPath)

    // Sort
    allTrades.sort((a, b) => {
      let aVal = a[sort], bVal = b[sort]
      if (['dca_count', 'holding_minutes', 'ep', 'pnl_usd', 'pnl_pct', 'fee_usd', 'index'].includes(sort)) {
        aVal = parseFloat(aVal); bVal = parseFloat(bVal)
      }
      if (typeof aVal === 'string') return order === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
      return order === 'asc' ? aVal - bVal : bVal - aVal
    })

    // Pagination
    const start = (page - 1) * limit
    const end = start + limit
    const paginated = allTrades.slice(start, end)

    res.json({
      trades: paginated,
      total: allTrades.length,
      page,
      limit,
      totalPages: Math.ceil(allTrades.length / limit)
    })
  } catch (error) {
    res.status(500).json({ error: error.message })
  }
})

app.listen(PORT, () => console.log(`🚀 Backend API on port ${PORT}`))
