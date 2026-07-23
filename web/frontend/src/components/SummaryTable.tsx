import React from 'react'

interface Props {
  data: any;
  symbol: string;
}

const SummaryTable: React.FC<Props> = ({ data, symbol }) => {
  if (!data || !data.stats) {
    return <div className="summary-empty">No data available</div>
  }

  const stats = data.stats
  const tradeSummary = data.trades_summary
  const margin = data.margin_analysis
  const sideBreak = data.side_breakdown || {}

  return (
    <div className="summary-section">
      <h2>📊 {symbol} Summary</h2>
      
      <div className="stats-grid">
        <div className="stat-card profit">
          <div className="stat-label">Total PnL</div>
          <div className="stat-value">${stats.total_pnl_usd?.toLocaleString()}</div>
        </div>
        
        <div className="stat-card dd">
          <div className="stat-label">Max Drawdown</div>
          <div className="stat-value">{stats.max_drawdown_pct?.toFixed(2)}%</div>
        </div>
        
        <div className="stat-card trades">
          <div className="stat-label">Total Trades</div>
          <div className="stat-value">{stats.total_trades}</div>
        </div>
        
        <div className="stat-card liq">
          <div className="stat-label">Win Rate</div>
          <div className="stat-value">{stats.win_rate}%</div>
        </div>
      </div>

      {tradeSummary && (
        <div className="trade-summary">
          <h3>DCA Details</h3>
          <table>
            <tbody>
              <tr><td>Max DCA:</td><td><strong>{tradeSummary.max_dca_count}</strong> ไม้</td></tr>
              <tr><td>Avg DCA:</td><td>{tradeSummary.avg_dca_count}</td></tr>
              <tr><td>Median DCA:</td><td>{tradeSummary.median_dca_count}</td></tr>
              <tr><td>Max Hold Time:</td><td>{tradeSummary.max_holding_minutes} นาที ({(tradeSummary.max_holding_minutes / 1440).toFixed(1)} วัน)</td></tr>
              <tr><td>TP Count:</td><td>{tradeSummary.tp_count}</td></tr>
              <tr><td>END Count:</td><td>{tradeSummary.end_count}</td></tr>
              <tr><td>Liquidations:</td><td className={tradeSummary.liquidations > 0 ? 'danger' : 'safe'}>{tradeSummary.liquidations}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      {margin && (
        <div className="margin-summary">
          <h3>Margin Analysis</h3>
          <table>
            <tbody>
              <tr><td>Max Margin Used:</td><td>${margin.max_margin_used_usd?.toLocaleString()}</td></tr>
              <tr><td>Free Margin:</td><td>${margin.free_margin_remaining?.toLocaleString()}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      {sideBreak && (
        <div className="side-breakdown">
          <h3>Side Breakdown</h3>
          <table>
            <thead>
              <tr><th>Side</th><th>Count</th><th>PnL</th><th>Max DCA</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>LONG</td>
                <td>{sideBreak.long?.count}</td>
                <td>${sideBreak.long?.pnl?.toLocaleString()}</td>
                <td>{sideBreak.long?.max_dca}</td>
              </tr>
              <tr>
                <td>SHORT</td>
                <td>{sideBreak.short?.count}</td>
                <td>${sideBreak.short?.pnl?.toLocaleString()}</td>
                <td>{sideBreak.short?.max_dca}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default SummaryTable
