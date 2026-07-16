import { useMemo, useState } from 'react'
import { Shield, Sparkles, X } from 'lucide-react'
import type { RuntimeState } from '@/types'
import { asRecord, asText } from './utils'

interface Props {
  state: RuntimeState
  busy?: boolean
  onClose: () => void
  onSave: (state: RuntimeState) => Promise<void>
}

const copyState = (state: RuntimeState): RuntimeState => JSON.parse(JSON.stringify(state)) as RuntimeState

export default function AdventureSetupModal({ state, busy, onClose, onSave }: Props) {
  const custom = asRecord(state.custom)
  const characters = asRecord(custom['角色列表'])
  const currentId = asText(custom['当前角色ID'], '')
  const current = asRecord(characters[currentId])
  const hp = asRecord(current['生命值'])
  const ac = asRecord(current['护甲等级'])
  const defaults = useMemo(() => ({
    name: currentId === '初始模板' ? '' : asText(current['姓名'], ''),
    race: asText(current['种族'], '人类'),
    className: asText(current['职业'], '战士'),
    background: asText(current['背景'], '流浪者'),
    alignment: asText(current['阵营'], '中立善良'),
    level: Number(current['等级'] || 1),
    hp: Number(hp['当前'] || state.player?.hp || 10),
    maxHp: Number(hp['最大'] || state.player?.max_hp || 10),
    ac: Number(ac['总值'] || state.player?.ac || 10),
  }), [current, currentId, hp, ac, state.player])
  const [form, setForm] = useState(defaults)
  const [saving, setSaving] = useState(false)

  const setField = (field: keyof typeof form, value: string | number) =>
    setForm((previous) => ({ ...previous, [field]: value }))

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    const name = form.name.trim() || '无名冒险者'
    const next = copyState(state)
    const nextCustom = asRecord(next.custom)
    const nextCharacters = { ...asRecord(nextCustom['角色列表']) }
    nextCharacters[name] = {
      ...asRecord(nextCharacters[name]),
      姓名: name,
      玩家名: asText(next.player?.name, ''),
      职业: form.className.trim(),
      种族: form.race.trim(),
      背景: form.background.trim(),
      阵营: form.alignment.trim(),
      等级: Math.max(1, Math.min(20, Number(form.level) || 1)),
      熟练加值: Math.ceil(Math.max(1, Math.min(20, Number(form.level) || 1)) / 4) + 1,
      护甲等级: { ...ac, 总值: Math.max(0, Math.min(99, Number(form.ac) || 10)) },
      生命值: {
        ...hp,
        当前: Math.max(0, Number(form.hp) || 0),
        最大: Math.max(1, Number(form.maxHp) || 1),
        临时: Number(hp['临时'] || 0),
      },
      状态: asRecord(current['状态']),
      资源: asRecord(current['资源']),
      物品: asRecord(current['物品']),
      施法: asRecord(current['施法']),
      笔记: asRecord(current['笔记']),
    }
    next.custom = { ...nextCustom, 当前角色ID: name, 角色列表: nextCharacters }
    next.player = {
      ...next.player,
      name,
      race: form.race.trim(),
      class: form.className.trim(),
      background: form.background.trim(),
      alignment: form.alignment.trim(),
      level: Math.max(1, Math.min(20, Number(form.level) || 1)),
      hp: Math.max(0, Number(form.hp) || 0),
      max_hp: Math.max(1, Number(form.maxHp) || 1),
      ac: Math.max(0, Math.min(99, Number(form.ac) || 10)),
    }
    next.scene = { ...next.scene, objective: '踏上冒险旅程' }
    setSaving(true)
    try {
      await onSave(next)
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="runtime-modal-backdrop" onMouseDown={onClose}>
      <form className="runtime-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <div className="runtime-modal__head">
          <div><Sparkles size={17}/><span><strong>创建冒险者</strong><small>原生安全角色创建器</small></span></div>
          <button type="button" onClick={onClose}><X size={17}/></button>
        </div>
        <div className="runtime-modal__body">
          <label>角色名称<input value={form.name} onChange={(e) => setField('name', e.target.value)} placeholder="例如：莱拉" autoFocus /></label>
          <div className="runtime-form-grid">
            <label>种族<input value={form.race} onChange={(e) => setField('race', e.target.value)} /></label>
            <label>职业<input value={form.className} onChange={(e) => setField('className', e.target.value)} /></label>
            <label>背景<input value={form.background} onChange={(e) => setField('background', e.target.value)} /></label>
            <label>阵营<input value={form.alignment} onChange={(e) => setField('alignment', e.target.value)} /></label>
            <label>等级<input type="number" min="1" max="20" value={form.level} onChange={(e) => setField('level', Number(e.target.value))} /></label>
            <label>护甲等级<input type="number" min="0" max="99" value={form.ac} onChange={(e) => setField('ac', Number(e.target.value))} /></label>
            <label>当前生命<input type="number" min="0" value={form.hp} onChange={(e) => setField('hp', Number(e.target.value))} /></label>
            <label>最大生命<input type="number" min="1" value={form.maxHp} onChange={(e) => setField('maxHp', Number(e.target.value))} /></label>
          </div>
          <p className="runtime-note"><Shield size={12}/>角色卡自带脚本不会执行；数据会保存进当前会话的原生状态。</p>
        </div>
        <div className="runtime-modal__foot">
          <button type="button" className="btn btn-secondary" onClick={onClose}>取消</button>
          <button type="submit" className="btn btn-primary" disabled={saving || busy}>{saving ? '保存中…' : '进入冒险'}</button>
        </div>
      </form>
    </div>
  )
}
