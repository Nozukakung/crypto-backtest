import React from 'react'

interface Run {
  id: string;
  time: string;
}

interface Props {
  runs: Run[];
  selected: string;
  onChange: (id: string) => void;
}

const RunSelector: React.FC<Props> = ({ runs, selected, onChange }) => {
  return (
    <div className="control-group">
      <label>📅 Select Backtest Run:</label>
      <select value={selected} onChange={(e) => onChange(e.target.value)}>
        <option value="latest">Latest Run</option>
        {runs.map(run => (
          <option key={run.id} value={run.id}>
            {run.time}
          </option>
        ))}
      </select>
    </div>
  )
}

export default RunSelector
