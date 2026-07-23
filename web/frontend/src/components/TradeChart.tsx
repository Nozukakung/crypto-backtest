import React from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ScatterChart, Scatter, AreaChart, Area, BarChart, Bar } from 'recharts'

interface Props {
  trades: any[];
  symbol: string;
}

const TradeChart: React.FC<Props> = ({ trades, symbol }) => {
  if (!trades || trades.length === 0) return null

  // เตรียมข้อมูล Equity Curve
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
            <Tooltip formatter={(value: number) => [`$${value.toFixed(2)}`, 'Cum PnL']} />
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
              <Tooltip formatter={(value: number) => [`$${value.toFixed(2)}`, 'PnL']} />
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
        <h3>Trades Log (Last 50)</h3>
        <table className="trades-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Side</th>
              <th>Open Time</th>
              <th>EP</th>
              <th>DCA</th>
              <th>PnL</th>
              <th>Hold (min)</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(-50).reverse().map((t, i) => (
              <tr key={i}>
                <td>{trades.length - i}</td>
                <td className={t.side === 'LONG' ? 'text-green' : 'text-red'}>{t.side}</td>
                <td>{t.open_time}</td>
                <td>${parseFloat(t.ep).toLocaleString()}</td>
                <td>{t.dca_count}</td>
                <td className={parseFloat(t.pnl_usd) >= 0 ? 'text-green' : 'text-red'}>
                  ${parseFloat(t.pnl_usd).toFixed(2)}
                </td>
                <td>{t.holding_minutes}</td>
                <td>{t.close_reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default TradeChart
