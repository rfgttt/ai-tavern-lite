import { Dices } from 'lucide-react'
import type { DiceResult } from '@/types'
import { asText } from './utils'

export default function DiceCard({ result }: { result: DiceResult }) {
  const title = asText(result.skill || result.label || result.reason, '检定')
  const details = asText(result.details || result.expression || result.formula || result.raw, '')
  const outcome = asText(result.result, result.total !== undefined ? `结果 ${result.total}` : '已掷骰')
  const success = /成功|命中|success|hit/i.test(outcome)
  return (
    <div className={`runtime-result-card ${success ? 'runtime-result-card--success' : ''}`}>
      <Dices size={16}/>
      <div className="min-w-0 flex-1">
        <strong>{title}</strong>
        {details ? <p>{details}</p> : null}
      </div>
      <span>{outcome}</span>
    </div>
  )
}
