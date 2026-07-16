import type { BattleSnapshot, BattleUnit, RuntimeState } from '@/types'

export const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}

export const asArray = <T = unknown>(value: unknown): T[] =>
  Array.isArray(value) ? (value as T[]) : []

export const asText = (value: unknown, fallback = '—'): string => {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return fallback
}

export const asNumber = (value: unknown, fallback = 0): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback

export const clampPercent = (value: unknown): number =>
  Math.max(0, Math.min(100, asNumber(value)))

export const activeDndCharacter = (state: RuntimeState): Record<string, unknown> => {
  const custom = asRecord(state.custom)
  const characters = asRecord(custom['角色列表'])
  const currentId = asText(custom['当前角色ID'], '')
  return asRecord(characters[currentId])
}

export const battleFromState = (state: RuntimeState): BattleSnapshot | null => {
  const combat = asRecord(state.combat)
  const units = asArray<BattleUnit>(combat.units)
  if (!combat.active && units.length === 0) return null
  return combat as BattleSnapshot
}

export const unitHp = (unit: BattleUnit): { current: number; maximum: number } => {
  const current = asNumber(unit.hp && typeof unit.hp === 'object' ? unit.hp.cur : unit.hp)
  const maximum = asNumber(
    unit.hp && typeof unit.hp === 'object' ? unit.hp.max : unit.max_hp,
    Math.max(current, 1)
  )
  return { current, maximum: Math.max(maximum, 1) }
}

export const unitPosition = (unit: BattleUnit): [number, number] => {
  const position = Array.isArray(unit.position) ? unit.position : unit.pos
  return [asNumber(position?.[0]), asNumber(position?.[1])]
}

export const unitName = (unit: BattleUnit): string => asText(unit.name || unit.id, '单位')
