import { Crosshair } from 'lucide-react'
import type { BattleCheckResult } from '@/types'
import { asText } from './utils'

export default function BattleCheckCard({ result }: { result: BattleCheckResult }) {
  const outcome = asText(result.outcome, '已结算')
  const success = /成功|命中|success|hit/i.test(outcome)
  return (
    <div className={`runtime-result-card ${success ? 'runtime-result-card--success' : 'runtime-result-card--danger'}`}>
      <Crosshair size={16}/>
      <div className="min-w-0 flex-1">
        <strong>{asText(result.actor, '行动者')} → {asText(result.target, '目标')}</strong>
        <p>{asText(result.action || result.check_type || result.details, '战斗检定')}</p>
      </div>
      <span>{outcome}</span>
    </div>
  )
}
