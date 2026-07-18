import type { SessionCacheEntry } from './types'

export const SESSION_CACHE_LIMIT = 6
export const SESSION_CACHE_FRESH_MS = 5_000

const inFlightRequests = new Map<string, Promise<unknown>>()

export const dedupeSessionRequest = <T>(key: string, factory: () => Promise<T>): Promise<T> => {
  const existing = inFlightRequests.get(key)
  if (existing) return existing as Promise<T>

  let request!: Promise<T>
  request = factory().finally(() => {
    if (inFlightRequests.get(key) === request) inFlightRequests.delete(key)
  })
  inFlightRequests.set(key, request)
  return request
}

export const isSessionCacheFresh = (
  entry: SessionCacheEntry | undefined,
  now = Date.now(),
): boolean => {
  if (!entry) return false
  const resourceTimestamps = [
    entry.messagesLoadedAt,
    entry.runtimeLoadedAt,
    entry.timelineLoadedAt,
  ]
  if (resourceTimestamps.every((timestamp) => timestamp === undefined)) {
    return now - entry.loadedAt < SESSION_CACHE_FRESH_MS
  }
  if (resourceTimestamps.some((timestamp) => typeof timestamp !== 'number')) {
    return false
  }
  return resourceTimestamps.every(
    (timestamp) => now - (timestamp as number) < SESSION_CACHE_FRESH_MS,
  )
}

export const mergeSessionCache = (
  cache: Record<string, SessionCacheEntry>,
  sessionId: string,
  patch: Partial<SessionCacheEntry>,
  activeSessionId?: string | null,
): Record<string, SessionCacheEntry> => {
  const current = cache[sessionId] || {
    messages: [],
    runtime: null,
    timeline: [],
    activeLorebook: [],
    loadedAt: 0,
  }
  const next = {
    ...cache,
    [sessionId]: {
      ...current,
      ...patch,
      loadedAt: Date.now(),
    },
  }

  const removable = Object.entries(next)
    .filter(([id]) => id !== sessionId && id !== activeSessionId)
    .sort(([, left], [, right]) => left.loadedAt - right.loadedAt)

  while (Object.keys(next).length > SESSION_CACHE_LIMIT && removable.length) {
    const [oldestId] = removable.shift()!
    delete next[oldestId]
  }

  return next
}

export const resetSessionReliability = () => {
  inFlightRequests.clear()
}
