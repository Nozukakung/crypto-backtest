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
  
  // สำหรับกราฟ และ pagination/sorting
  const [allTradesData, setAllTradesData] = useState<any[]>([]) // ข้อมูลทั้งหมด (ใช้ในการวาดกราฟ)
  const [paginatedTrades, setPaginatedTrades] = useState<any[]>([]) // ข้อมูลเฉพาะหน้านี้
  const [totalTrades, setTotalTrades] = useState<number>(0)
  const [page, setPage] = useState<number>(1)
  const [limit, setLimit] = useState<number>(50)
  const [sort, setSort] = useState<string>('open_time')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')

  const [selectedSymbol, setSelectedSymbol] = useState<string>('BTCUSDT')
  const [loading, setLoading] = useState<boolean>(false)

  // 1. ดึงรายการ Runs ทั้งหมดเมื่อโหลดหน้าครั้งแรก
  useEffect(() => {
    fetch(`${API_URL}/runs`)
      .then(res => res.json())
      .then(data => setRuns(data))
      .catch(err => console.error('Failed to load runs:', err))
  }, [])

  // reset page เมื่อเปลี่ยนเหรียญหรือ run
  useEffect(() => {
    setPage(1)
  }, [selectedRun, selectedSymbol])

  // 2. ดึง Stats และข้อมูล Trades สำหรับวาดกราฟ (ดึงครั้งเดียวเมื่อสลับเหรียญ/run)
  useEffect(() => {
    if (!selectedRun || !selectedSymbol) return
    setLoading(true)

    // ดึง stats รายเหรียญ
    const fetchStats = fetch(`${API_URL}/runs/${selectedRun}/stats/${selectedSymbol}`)
      .then(res => res.ok ? res.json() : Promise.reject())
      .then(data => setSummary(data))
      .catch(() => {
        return fetch(`${API_URL}/runs/${selectedRun}`)
          .then(res => res.json())
          .then(data => setSummary(data))
      })

    // ดึง Trades ทั้งหมด (แบบไม่แบ่งหน้า เพื่อให้วาดกราฟ Cumulative PnL ครบถ้วน)
    // แต่ดึงแบบจำกัด bandwidth โดยดึงจาก API ปกติที่ limit=999999
    const fetchAllTrades = fetch(`${API_URL}/runs/${selectedRun}/trades/${selectedSymbol}?limit=50000`)
      .then(res => res.json())
      .then(data => {
        setAllTradesData(data.trades || [])
      })
      .catch(err => {
        console.error(err)
        setAllTradesData([])
      })

    Promise.all([fetchStats, fetchAllTrades]).finally(() => {
      setLoading(false)
    })
  }, [selectedRun, selectedSymbol])

  // 3. ดึง Trades รายหน้า (Pagination + Sorting)
  useEffect(() => {
    if (!selectedRun || !selectedSymbol) return
    
    fetch(`${API_URL}/runs/${selectedRun}/trades/${selectedSymbol}?page=${page}&limit=${limit}&sort=${sort}&order=${order}`)
      .then(res => res.json())
      .then(data => {
        setPaginatedTrades(data.trades || [])
        setTotalTrades(data.total || 0)
      })
      .catch(err => {
        console.error(err)
        setPaginatedTrades([])
      })
  }, [selectedRun, selectedSymbol, page, limit, sort, order])

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

      {allTradesData.length > 0 && (
        <TradeChart 
          trades={allTradesData} 
          paginatedTrades={paginatedTrades}
          total={totalTrades}
          page={page}
          limit={limit}
          sort={sort}
          order={order}
          setPage={setPage}
          setLimit={setLimit}
          setSort={setSort}
          setOrder={setOrder}
          symbol={selectedSymbol} 
        />
      )}
    </div>
  )
}

export default App
