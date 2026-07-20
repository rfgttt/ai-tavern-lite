import type { RuntimeState, TurnRuntime } from '@/types'

export const TECHNICAL_KEYS = new Set([
  'runtime', 'runtime_version', 'mode', 'model', 'provider', 'schema', 'version',
  'metadata', 'meta', 'system', 'config', 'configuration', 'relation', 'relationship',
  'scene', 'quests', 'quest', 'tasks', 'task', 'inventory', 'items', 'combat', 'battle',
  'character', 'player',
])

export const PLACEHOLDER_TEXT = new Set([
  '', '未命名场景', '当前', '环境平稳', '周围平静', '平静', '正常', '未知', '—',
])

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)

export const hasContent = (value: unknown): boolean => {
  if (value == null) return false
  if (typeof value === 'string') return Boolean(value.trim()) && !PLACEHOLDER_TEXT.has(value.trim())
  if (Array.isArray(value)) return value.some(hasContent)
  if (isRecord(value)) return Object.values(value).some(hasContent)
  return true
}

export const sameValue = (left: unknown, right: unknown): boolean => {
  try { return JSON.stringify(left) === JSON.stringify(right) } catch { return left === right }
}

export const pickAlias = (source: unknown, aliases: string[]): unknown => {
  if (!isRecord(source)) return undefined
  for (const alias of aliases) {
    if (alias in source) return source[alias]
    const found = Object.keys(source).find((key) => key.toLowerCase() === alias.toLowerCase())
    if (found) return source[found]
  }
  return undefined
}

export const sectionValue = (state: RuntimeState, root: string, aliases: string[] = []): unknown => {
  const direct = state[root]
  if (hasContent(direct)) return direct
  return pickAlias(state.custom, [root, ...aliases])
}

export interface RuntimeActivity {
  changed: boolean
  turnsAgo: number | null
  operationCount: number
  event: string
}

export const activityForRoots = (timeline: TurnRuntime[], roots: string[]): RuntimeActivity => {
  const normalized = roots.map((root) => root.toLowerCase())
  for (let index = timeline.length - 1; index >= 0; index -= 1) {
    const turn = timeline[index]
    const operations = turn.patch.filter((operation) => {
      const path = String(operation.path || '').toLowerCase()
      return normalized.some((root) =>
        path === `/${root}` || path.startsWith(`/${root}/`) ||
        path === `/custom/${root}` || path.startsWith(`/custom/${root}/`)
      )
    })
    if (operations.length) {
      return {
        changed: true,
        turnsAgo: timeline.length - 1 - index,
        operationCount: operations.length,
        event: turn.events[0] || '',
      }
    }
  }
  return { changed: false, turnsAgo: null, operationCount: 0, event: '' }
}

export const activityLabel = (activity: RuntimeActivity): string => {
  if (!activity.changed) return '尚未收到更新'
  if (activity.turnsAgo === 0) return `本轮更新 ${activity.operationCount} 项`
  return `${activity.turnsAgo} 轮前更新`
}

export const changedFromInitial = (current: unknown, initial: unknown): boolean =>
  hasContent(current) && !sameValue(current, initial)

const MVU_DESCRIPTION_HINT = /当前|说明|描述|格式|程度|列表|记录|范围|状态|变量|用于|发生|\[0-100\]/i

export const presentCardValue = (value: unknown): unknown => {
  if (Array.isArray(value)) {
    const cleaned = value.filter((item) => item !== '$__META_EXTENSIBLE__$')
    if (cleaned.length === 2 && typeof cleaned[1] === 'string' && MVU_DESCRIPTION_HINT.test(cleaned[1])) {
      return presentCardValue(cleaned[0])
    }
    return cleaned.map(presentCardValue).filter(hasContent)
  }
  if (isRecord(value)) {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !key.startsWith('$'))
        .map(([key, item]) => [key, presentCardValue(item)])
        .filter(([, item]) => hasContent(item)),
    )
  }
  return value
}

export const sanitizedCustom = (custom: unknown): Record<string, unknown> => {
  if (!isRecord(custom)) return {}
  return presentCardValue(Object.fromEntries(
    Object.entries(custom).filter(([key, value]) =>
      !TECHNICAL_KEYS.has(key.toLowerCase()) && hasContent(value)
    )
  )) as Record<string, unknown>
}

export const humanPath = (path: unknown): string => {
  const labels: Record<string, string> = {
    scene: '场景', relationship: '关系', quests: '任务', inventory: '物品', combat: '战斗',
    character: '角色状态', player: '玩家状态', custom: '卡片数据', affection: '好感',
    trust: '信任', tension: '张力', mood: '情绪', expression: '表情', location: '地点',
    weather: '环境', atmosphere: '氛围', objective: '当前目标',
  }
  return String(path || '')
    .split('/').filter(Boolean)
    .map((part) => labels[part] || part.replace(/~1/g, '/').replace(/~0/g, '~'))
    .join(' › ')
}
