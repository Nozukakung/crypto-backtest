import { useState, useEffect } from 'react'
import RunSelector from './components/RunSelector'
import SymbolSelector from './components/SymbolSelector'
import SummaryTable from './components/SummaryTable'
import TradeChart from './components/TradeChart'
import './App.css'

const API_URL = 'http://localhost:5001/api'

interface Run {
  id: string;
  time: string;
  summary?: any;
}

function App() {
  const [runs, setRuns] = useState<Run[]>([])
  const [selectedRun, setSelectedRun] = useState<string>('latest')
  const [summary, setSummary] = useState<any>(null)
  const [trades, setTrades] = useState<any[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTCUSDT')
  const [loading, setLoading] = useState<boolean>(false)

  // 1. ดึงรายการ Runs ทั้งหมดเมื่อโหลดหน้าครั้งแรก (ครั้งเดียว)
  useEffect(() => {
    fetch(`${API_URL}/runs`)
      .then(res => res.json())
      .then(data => {
        setRuns(data)
      })
      .catch(err => console.error('Failed to load runs:', err))
  }, [])

  // 2. ดึงข้อมูล Stats และ Trades ควบคู่กันเมื่อเลือก Run หรือ Symbol เปลี่ยน (ห้ามแยก useEffect ซ้ำซ้อน)
  useEffect(() => {
    if (!selectedRun || !selectedSymbol) return
    
    setLoading(true)
    
    // ดึง Stats เหรียญที่เลือก
    const fetchStats = fetch(`${API_URL}/runs/${selectedRun}/stats/${selectedSymbol}`)
      .then(res => {
        if (!res.ok) throw new Error('Stats not found')
        return res.json()
      })
      .then(data => {
        setSummary(data)
      })
      .catch(err => {
        console.warn('Per-symbol stats failed, falling back to general run info:', err)
        // Fallback
        return fetch(`${API_URL}/runs/${selectedRun}`)
          .then(res => res.json())
          .then(data => {
            setSummary(data)
          })
      })

    // ดึง Trades ของเหรียญที่เลือก
    const fetchTrades = fetch(`${API_URL}/runs/${selectedRun}/trades/${selectedSymbol}`)
      .then(res => {
        if (!res.ok) throw new Error('Trades not found')
        return res.json()
      })
      .then(data => {
        setTrades(data)
      })
      .catch(err => {
        console.error(err)
        setTrades([])
      })

    // เมื่อเสร็จทั้งสองอัน ค่อยเอา Loading ออก
    Promise.all([fetchStats, fetchTrades]).finally(() => {
      setLoading(false)
    })

  }, [selectedRun, selectedSymbol])

  return (
    <div className="app">
      <header className="header">
        <h1>📈 Crypto Backtest Dashboard</h1>
        <p className="subtitle">Mean Reversion + DCA — ตาเล็ก 98SE</p>
      </header>

      <div className="controls">
        <RunSelector
          runs={runs}
          selected={selectedRun}
          onChange={setSelectedRun}
        />
        <SymbolSelector
          selected={selectedSymbol}
          onChange={setSelectedSymbol}
        />
      </div>

      {loading && <div className="loading">⏳ Loading...</div>}

      {!loading && summary && (
        <SummaryTable data={summary} symbol={selectedSymbol} />
      )}

      {!loading && trades.length > 0 && (
        <TradeChart trades={trades} symbol={selectedSymbol} />
      )}
    </div>
  )
}

export default App
