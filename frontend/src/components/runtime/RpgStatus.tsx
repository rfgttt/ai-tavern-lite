import { HeartPulse, Shield, Swords, UserRound, Sparkles } from 'lucide-react'
import type { RuntimeState } from '@/types'
import { activeDndCharacter, asArray, asNumber, asRecord, asText } from './utils'

interface Props { state: RuntimeState }

export default function RpgStatus({ state }: Props) {
  const player = state.player || {}
  const dnd = activeDndCharacter(state)
  const hpRecord = asRecord(dnd['生命值'])
  const acRecord = asRecord(dnd['护甲等级'])
  const name = asText(dnd['姓名'], asText(player.name, '冒险者'))
  const className = asText(dnd['职业'], asText(player.class, '未选择职业'))
  const race = asText(dnd['种族'], asText(player.race, '未选择种族'))
  const level = asNumber(dnd['等级'], asNumber(player.level, 1))
  const hp = asNumber(hpRecord['当前'], asNumber(player.hp, 10))
  const maxHp = Math.max(1, asNumber(hpRecord['最大'], asNumber(player.max_hp, 10)))
  const ac = asNumber(acRecord['总值'], asNumber(player.ac, 10))
  const conditions = [
    ...asArray<string>(player.conditions),
    ...Object.keys(asRecord(dnd['状态'])),
  ].filter(Boolean)

  return (
    <section className="runtime-card">
      <div className="runtime-section-title">
        <UserRound size={15} />
        <span>冒险者档案</span>
        <span className="tag ml-auto">Lv.{level}</span>
      </div>
      <div className="runtime-character-line">
        <div className="runtime-character-emblem">{name.charAt(0)}</div>
        <div className="min-w-0">
          <strong className="block truncate text-tavern-text-primary">{name}</strong>
          <span className="text-xs text-tavern-text-muted">{race} · {className}</span>
        </div>
      </div>
      <div className="runtime-stat-grid mt-3">
        <div><HeartPulse size={14}/><span>HP</span><strong>{hp}/{maxHp}</strong></div>
        <div><Shield size={14}/><span>AC</span><strong>{ac}</strong></div>
        <div><Swords size={14}/><span>等级</span><strong>{level}</strong></div>
      </div>
      <div className="runtime-meter mt-3">
        <div className="runtime-meter__head"><span><HeartPulse size={13}/>生命状态</span><strong>{Math.round((hp / maxHp) * 100)}%</strong></div>
        <div className="runtime-meter__track"><div className="runtime-meter__fill runtime-meter__fill--hp" style={{ width: `${Math.max(0, Math.min(100, (hp / maxHp) * 100))}%` }}/></div>
      </div>
      {conditions.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {conditions.map((condition) => <span className="tag" key={condition}><Sparkles size={10}/>{condition}</span>)}
        </div>
      ) : null}
    </section>
  )
}
