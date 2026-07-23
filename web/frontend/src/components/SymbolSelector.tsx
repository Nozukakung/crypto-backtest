import React from 'react'

interface Props {
  selected: string;
  onChange: (sym: string) => void;
}

const SymbolSelector: React.FC<Props> = ({ selected, onChange }) => {
  const symbols = ['BTCUSDT', 'DOGEUSDT', 'BNBUSDT', 'ETHUSDT']

  return (
    <div className="control-group">
      <label>🪙 Select Symbol:</label>
      <select value={selected} onChange={(e) => onChange(e.target.value)}>
        {symbols.map(sym => (
          <option key={sym} value={sym}>
            {sym}
          </option>
        ))}
      </select>
    </div>
  )
}

export default SymbolSelector
