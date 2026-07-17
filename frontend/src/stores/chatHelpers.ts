import type {
  Message,
  RuntimeSession,
  StreamDoneEvent,
  StreamRuntimeEvent,
  TurnRuntime,
} from '@/types'

export const createLocalMessage = (
  sessionId: string,
  role: Message['role'],
  content: string,
  sequence: number,
  generationStatus: Message['generation_status'] = 'complete',
): Message => {
  const now = new Date().toISOString()
  return {
    id: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    session_id: sessionId,
    role,
    content,
    sequence,
    generation_status: generationStatus,
    created_at: now,
    updated_at: now,
  }
}

export const mergeTurn = (timeline: TurnRuntime[], turn: TurnRuntime): TurnRuntime[] => {
  const withoutCurrent = timeline.filter((item) => item.message_id !== turn.message_id)
  return [...withoutCurrent, turn].sort((a, b) => {
    const aTime = a.created_at ? Date.parse(a.created_at) : 0
    const bTime = b.created_at ? Date.parse(b.created_at) : 0
    return aTime - bTime
  })
}

export const runtimeFromEvent = (
  current: RuntimeSession | null,
  sessionId: string,
  event: StreamRuntimeEvent,
): RuntimeSession => ({
  session_id: sessionId,
  profile: event.profile,
  initial_state: current?.initial_state || event.state,
  state: event.state,
  revision: event.revision,
  last_turn: current?.last_turn || null,
  updated_at: current?.updated_at || null,
})

export const runtimeAfterDone = (
  current: RuntimeSession | null,
  sessionId: string,
  event: StreamDoneEvent,
): RuntimeSession | null => {
  if (!current) return null
  return {
    ...current,
    session_id: sessionId,
    state: event.state,
    revision: event.revision,
    last_turn: event.runtime || current.last_turn,
    updated_at: new Date().toISOString(),
  }
}
