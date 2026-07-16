import { Map, Swords } from 'lucide-react'
import type { BattleSnapshot, BattleUnit } from '@/types'
import { asArray, asNumber, asText, unitHp, unitName, unitPosition } from './utils'

const attitudeClass = (unit: BattleUnit) => {
  if (unit.faction === 'friendly' || unit.attitude === 0) return 'battle-token--friendly'
  if (unit.faction === 'hostile' || unit.attitude === 2) return 'battle-token--hostile'
  return 'battle-token--neutral'
}

export default function BattleMap({ battle }: { battle: BattleSnapshot }) {
  const units = asArray<BattleUnit>(battle.units)
  if (!units.length) return null
  const positions = units.map(unitPosition)
  const maxX = Math.max(...positions.map(([x]) => x), 20)
  const maxY = Math.max(...positions.map(([, y]) => y), 20)

  return (
    <section className="battle-panel">
      <div className="runtime-section-title px-3 pt-3">
        <Map size={15}/><span>{asText(battle.title, '战斗快照')}</span>
        <span className="tag ml-auto"><Swords size={10}/>回合 {asNumber(battle.round, 0)}</span>
      </div>
      <div className="battle-map" role="img" aria-label="战斗单位位置快照">
        {units.map((unit, index) => {
          const [x, y] = unitPosition(unit)
          const hp = unitHp(unit)
          const active = unit.next || battle.active_unit === unit.id || battle.turn === unit.id
          return (
            <div
              key={`${unitName(unit)}-${index}`}
              className={`battle-token ${attitudeClass(unit)} ${active ? 'battle-token--active' : ''}`}
              style={{ left: `${8 + (x / Math.max(maxX, 1)) * 82}%`, top: `${10 + (y / Math.max(maxY, 1)) * 76}%` }}
              title={`${unitName(unit)} HP ${hp.current}/${hp.maximum}`}
            >
              <span>{unitName(unit).slice(0, 2)}</span>
              <small>{hp.current}/{hp.maximum}</small>
            </div>
          )
        })}
      </div>
      <div className="battle-legend">
        {units.map((unit, index) => {
          const hp = unitHp(unit)
          return <span key={`${unitName(unit)}-legend-${index}`}><i className={attitudeClass(unit)}/>{unitName(unit)} {hp.current}/{hp.maximum}</span>
        })}
      </div>
    </section>
  )
}
