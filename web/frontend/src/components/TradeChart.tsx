import React from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ScatterChart, Scatter, AreaChart, Area, BarChart, Bar } from 'recharts'

interface Props {
  trades: any[];          // ทั้งหมด (สำหรับวาดกราฟ)
  paginatedTrades: any[]; // เฉพาะหน้าปัจจุบัน (แสดงในตาราง)
  total: number;
  page: number;
  limit: number;
  sort: string;
  order: 'asc' | 'desc';
  setPage: (p: number) => void;
  setLimit: (l: number) => void;
  setSort: (s: string) => void;
  setOrder: (o: 'asc' | 'desc') => void;
  symbol: string;
}

const TradeChart: React.FC<Props> = ({ 
  trades, 
  paginatedTrades, 
  total, 
  page, 
  limit, 
  sort, 
  order, 
  setPage, 
  setLimit, 
  setSort, 
  setOrder, 
  symbol 
}) => {
  
  const toggleSort = (key: string) => {
    if (sort === key) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(key)
      setOrder('desc')
    }
  }

  const sortIndicator = (key: string) => {
    if (sort !== key) return ' ↕'
    return order === 'asc' ? ' ↑' : ' ↓'
  }

  // ฟังก์ชันจัดรูปแบบเวลาถือครองให้อ่านง่าย
  const formatHoldingTime = (minutesStr: any) => {
    const totalMinutes = parseInt(minutesStr || 0)
    if (isNaN(totalMinutes) || totalMinutes <= 0) return '0m'

    const d = Math.floor(totalMinutes / 1440)
    const h = Math.floor((totalMinutes % 1440) / 60)
    const m = totalMinutes % 60

    if (d > 0) {
      return `${d}d ${h}h`
    } else if (h > 0) {
      return `${h}h ${m}m`
    }
    return `${m}m`
  }

  if (!trades || trades.length === 0) return null

  // เตรียมข้อมูล Equity Curve (วาดกราฟ)
  let cumPnl = 0
  const equityData = trades.map((t, i) => {
    cumPnl += parseFloat(t.pnl_usd || 0)
    return {
      index: i + 1,
      pnl: parseFloat(t.pnl_usd || 0),
      cumPnl: parseFloat(cumPnl.toFixed(2)),
      dcaCount: parseInt(t.dca_count || 0),
      openTime: t.open_time,
      side: t.side,
      closeReason: t.close_reason
    }
  })

  // เตรียมข้อมูล DCA Distribution
  const dcaCounts = trades.map(t => parseInt(t.dca_count || 0))
  const maxDca = Math.max(...dcaCounts)
  const dcaBuckets: { [key: string]: number } = {}
  for (let i = 0; i <= Math.min(maxDca, 50); i++) {
    dcaBuckets[i] = 0
  }
  dcaCounts.forEach(d => {
    const bucket = d > 50 ? '50+' : d.toString()
    if (bucket === '50+') {
      dcaBuckets['50+'] = (dcaBuckets['50+'] || 0) + 1
    } else {
      dcaBuckets[bucket]++
    }
  })
  const dcaDistData = Object.entries(dcaBuckets)
    .map(([key, value]) => ({ dca: key, count: value }))

  // กำไร LONG vs SHORT
  const longTrades = equityData.filter(t => t.side === 'LONG')
  const shortTrades = equityData.filter(t => t.side === 'SHORT')

  const totalPages = Math.ceil(total / limit)

  return (
    <div className="charts-section">
      <h2>📈 Trade Analysis - {symbol}</h2>
      
      <div className="chart-container">
        <h3>Cumulative PnL Over Trades</h3>
        <ResponsiveContainer width="100%" height={350}>
          <AreaChart data={equityData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="index" label={{ value: 'Trade #', position: 'bottom', offset: -5 }} />
            <YAxis label={{ value: 'USD', angle: -90, position: 'insideLeft' }} />
            <Tooltip formatter={(value: any) => [`$${parseFloat(value).toFixed(2)}`, 'Cum PnL']} />
            <Area type="monotone" dataKey="cumPnl" stroke="#22c55e" fill="rgba(34,197,94,0.3)" name="Cumulative PnL" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-row">
        <div className="chart-container half">
          <h3>DCA Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={dcaDistData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="dca" label={{ value: 'DCA Count', position: 'bottom', offset: -5 }} />
              <YAxis label={{ value: 'Count', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Bar dataKey="count" fill="#3b82f6" name="Trades" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-container half">
          <h3>PnL per Trade</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="index" name="Trade" />
              <YAxis dataKey="pnl" name="PnL" label={{ value: 'USD', angle: -90, position: 'insideLeft' }} />
              <Tooltip formatter={(value: any) => [`$${parseFloat(value).toFixed(2)}`, 'PnL' as any]} />
              <Scatter data={longTrades} fill="#22c55e" name="LONG" />
              <Scatter data={shortTrades} fill="#ef4444" name="SHORT" />
            </ScatterChart>
          </ResponsiveContainer>
          <div className="legend-inline">
            <span className="legend-item"><span className="dot green"></span> LONG</span>
            <span className="legend-item"><span className="dot red"></span> SHORT</span>
          </div>
        </div>
      </div>

      <div className="trades-table-container">
        <div className="trades-table-header">
          <h3>Trades Log ({total.toLocaleString()} total)</h3>
          <div className="table-controls">
            <div className="page-size-selector">
              <label>Show: </label>
              <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
                <option value={500}>500</option>
              </select>
            </div>
          </div>
        </div>

        <table className="trades-table">
          <thead>
            <tr>
              <th onClick={() => toggleSort('index')} className="sortable">#{sortIndicator('index')}</th>
              <th onClick={() => toggleSort('side')} className="sortable">Side{sortIndicator('side')}</th>
              <th onClick={() => toggleSort('open_time')} className="sortable">Open Time{sortIndicator('open_time')}</th>
              <th onClick={() => toggleSort('ep')} className="sortable">EP{sortIndicator('ep')}</th>
              <th onClick={() => toggleSort('dca_count')} className="sortable">DCA{sortIndicator('dca_count')}</th>
              <th onClick={() => toggleSort('pnl_usd')} className="sortable">PnL{sortIndicator('pnl_usd')}</th>
              <th onClick={() => toggleSort('holding_minutes')} className="sortable">Hold Time{sortIndicator('holding_minutes')}</th>
              <th onClick={() => toggleSort('close_reason')} className="sortable">Reason{sortIndicator('close_reason')}</th>
            </tr>
          </thead>
          <tbody>
            {paginatedTrades.map((t, i) => (
              <tr key={i}>
                <td>{t.index || (total - ((page - 1) * limit) - i)}</td>
                <td className={t.side === 'LONG' ? 'text-green' : 'text-red'}>{t.side}</td>
                <td>{t.open_time}</td>
                <td>${parseFloat(t.ep).toLocaleString()}</td>
                <td>{t.dca_count}</td>
                <td className={parseFloat(t.pnl_usd) >= 0 ? 'text-green' : 'text-red'}>
                  ${parseFloat(t.pnl_usd).toFixed(2)}
                </td>
                <td className={parseInt(t.holding_minutes) >= 10080 ? 'hold-critical' : parseInt(t.holding_minutes) >= 1440 ? 'hold-warn' : ''}>
                  {formatHoldingTime(t.holding_minutes)}
                </td>
                <td>{t.close_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination UI */}
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
            ◀ Prev
          </button>
          <span>Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Next ▶
          </button>
        </div>
      </div>
    </div>
  )
}

export default TradeChart
