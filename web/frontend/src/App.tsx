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

  // ดึงรายการ Runs
  useEffect(() => {
    fetch(`${API_URL}/runs`)
      .then(res => res.json())
      .then(data => {
        setRuns(data)
      })
      .catch(err => console.error('Failed to load runs:', err))
  }, [])

  // ดึง summary ของ Run ที่เลือก
  useEffect(() => {
    if (!selectedRun) return
    setLoading(true)
    fetch(`${API_URL}/runs/${selectedRun}`)
      .then(res => res.json())
      .then(data => {
        setSummary(data)
        setLoading(false)
      })
      .catch(err => {
        console.error(err)
        setLoading(false)
      })
  }, [selectedRun])

  // ดึง trades ของเหรียญที่เลือก
  useEffect(() => {
    if (!selectedRun || !selectedSymbol) return
    setLoading(true)
    fetch(`${API_URL}/runs/${selectedRun}/trades/${selectedSymbol}`)
      .then(res => res.json())
      .then(data => {
        setTrades(data)
        setLoading(false)
      })
      .catch(err => {
        console.error(err)
        setTrades([])
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
