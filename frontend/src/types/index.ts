export interface Character {
  id: string
  name: string
  description: string
  personality: string
  scenario: string
  first_message: string
  avatar_path: string
  created_at: string
  updated_at: string
}

export interface CharacterDraft {
  name: string
  description: string
  personality: string
  scenario: string
  first_message: string
}

export interface ChatSession {
  id: string
  character_id: string
  persona_id?: string | null
  group_id?: string | null
  title: string
  created_at: string
  updated_at: string
}

export interface CharacterSessionOptions {
  character_id: string
  character_name: string
  greetings: string[]
  runtime_profile: Record<string, unknown>
  initial_state: RuntimeState
}

export interface SessionCreateOptions {
  title?: string
  persona_id?: string
  group_id?: string
  use_default_persona?: boolean
  opening_message?: string
  skip_opening_message?: boolean
  initial_state?: RuntimeState
}

export type MessageSegment =
  | { type: 'dialogue'; speaker: string; text: string; emotion?: string }
  | { type: 'narration' | 'thought' | 'markdown'; text: string }
  | { type: 'action'; speaker?: string; text: string }
  | { type: 'card-state-placeholder' }

export interface MessageArtifact {
  type: 'dice' | 'battle-check' | 'battle-map' | 'state-diff' | 'generic'
  data: unknown
}

export interface Message {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  sequence: number
  generation_status: 'complete' | 'generating' | 'stopped' | 'error'
  segments?: MessageSegment[]
  artifacts?: MessageArtifact[]
  speaker_metadata?: Record<string, { color?: string; avatar?: string; [key: string]: unknown }>
  render_version?: number
  created_at: string
  updated_at: string
}

export interface Memory {
  id: string
  character_id: string | null
  session_id: string | null
  category: string
  content: string
  importance: number
  keywords: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface LorebookEntry {
  id?: number
  keys: string[]
  secondary_keys: string[]
  comment: string
  content: string
  constant: boolean
  selective: boolean
  enabled: boolean
  insertion_order: number
  position: string
  use_regex: boolean
  probability: number
  extensions: Record<string, unknown>
}

export interface Lorebook {
  entries: LorebookEntry[]
}

export interface AppSettings {
  provider_name: string
  base_url: string
  model: string
  temperature: number
  top_p: number
  max_tokens: number
  context_window: number
  username: string
  mock_llm: boolean
  auto_memory_extraction: boolean
  api_key_configured: boolean
  api_key_masked: string
  custom_headers: Record<string, string>
  settings_writable: boolean
  diagnostics_enabled: boolean
  selftest_enabled: boolean
}

export type RuntimeMode = 'relationship' | 'adventure' | 'general'

export interface RuntimeProfile {
  version: number
  mode: RuntimeMode
  card_spec: string
  card_spec_version: string
  capabilities: Record<string, boolean>
  native_renderers: string[]
  script_execution: 'disabled'
  regex_script_count: number
  lorebook_entry_count: number
  external_resource_count: number
  warnings: string[]
}

export interface SceneRuntimeState {
  location?: string
  time?: string
  weather?: string
  atmosphere?: string
  objective?: string
  [key: string]: unknown
}

export interface CharacterRuntimeState {
  mood?: string
  expression?: string
  outfit?: string
  posture?: string
  goal?: string
  [key: string]: unknown
}

export interface RelationshipRuntimeState {
  affection?: number
  trust?: number
  tension?: number
  stage?: string
  attitude?: string
  [key: string]: unknown
}

export interface PlayerRuntimeState {
  name?: string
  class?: string
  race?: string
  background?: string
  alignment?: string
  level?: number
  hp?: number
  max_hp?: number
  ac?: number
  conditions?: string[]
  stats?: Record<string, number>
  [key: string]: unknown
}

export interface BattleUnit {
  id?: string
  name?: string
  faction?: 'friendly' | 'hostile' | 'neutral' | string
  attitude?: number
  init?: number
  initiative?: number
  hp?: { cur?: number; max?: number } | number
  max_hp?: number
  pos?: [number, number] | number[]
  position?: [number, number] | number[]
  next?: boolean
  status?: string[]
  portrait?: string
  [key: string]: unknown
}

export interface BattleSnapshot {
  title?: string
  theme?: string
  grid_ft?: number
  cols?: number
  rows?: number
  units?: BattleUnit[]
  terrain?: Array<Record<string, unknown>>
  events?: string[]
  active_unit?: string
  [key: string]: unknown
}

export interface RuntimeState {
  scene?: SceneRuntimeState
  character?: CharacterRuntimeState
  relationship?: RelationshipRuntimeState
  player?: PlayerRuntimeState
  quests?: unknown[] | Record<string, unknown>
  inventory?: unknown[] | Record<string, unknown>
  combat?: BattleSnapshot | Record<string, unknown>
  custom?: Record<string, unknown>
  [key: string]: unknown
}

export interface LorebookTrigger {
  id?: number | string
  title?: string
  comment?: string
  keys?: string[]
  position?: string
  content_preview?: string
  trigger_type?: string
  estimated_tokens?: number
  injected?: boolean
  [key: string]: unknown
}

export interface DiceResult {
  expression?: string
  formula?: string
  total?: number
  result?: number
  rolls?: number[]
  label?: string
  reason?: string
  raw?: string
  [key: string]: unknown
}

export interface BattleCheckResult {
  actor?: string
  target?: string
  check?: string
  roll?: number
  modifier?: number
  total?: number
  dc?: number
  outcome?: string
  damage?: number
  raw?: string
  [key: string]: unknown
}

export interface TurnRuntime {
  id: string
  message_id: string
  state_before: RuntimeState
  patch: Array<Record<string, unknown>>
  state_after: RuntimeState
  events: string[]
  choices: string[]
  dice: DiceResult[]
  battle_checks: BattleCheckResult[]
  battle: BattleSnapshot | null
  expression: string
  triggered_lorebook: LorebookTrigger[]
  rejected_patch: Array<Record<string, unknown>>
  parser_errors: string[]
  created_at: string | null
}

export interface RuntimeSession {
  session_id: string
  profile: RuntimeProfile
  initial_state: RuntimeState
  state: RuntimeState
  revision: number
  last_turn: TurnRuntime | null
  updated_at: string | null
}

export interface StreamRuntimeEvent {
  type: 'runtime'
  request_id?: string
  session_id: string
  profile: RuntimeProfile
  state: RuntimeState
  revision: number
  triggered_lorebook: LorebookTrigger[]
}

export interface StreamMessageEvent {
  type: 'message'
  request_id?: string
  user_message: Message | null
  assistant_message: Message
}

export interface StreamDoneEvent {
  type: 'done'
  request_id?: string
  message_id: string
  status: Message['generation_status']
  content: string
  runtime: TurnRuntime | null
  state: RuntimeState
  revision: number
  segments?: MessageSegment[]
  artifacts?: MessageArtifact[]
  speaker_metadata?: Record<string, { color?: string; avatar?: string; [key: string]: unknown }>
  render_version?: number
}

export interface PromptSection {
  name: string
  content: string
  estimated_tokens: number
  source: string
}

export interface PromptPreview {
  sections: PromptSection[]
  total_estimated_tokens: number
  context_budget: number
}

export interface ConnectionTestResult {
  success: boolean
  message: string
  model?: string
}

export interface DiagnosticComponents {
  backend: boolean
  database: boolean
  frontend_build: boolean
  provider_configured: boolean
  state_engine: boolean
  log_writable: boolean
}

export interface DiagnosticHealth {
  status: 'ok' | 'degraded'
  version: string
  checked_at: string
  mock_mode: boolean
  provider: string
  model: string
  components: DiagnosticComponents
}

export interface DiagnosticTiming {
  first_token_ms: number | null
  total_ms: number
}

export interface DiagnosticPromptSummary {
  message_count: number
  estimated_tokens: number
  context_budget: number
  worldbook_entries: number
  worldbook_titles: string[]
  memories_injected: number
  history_messages: number
  history_trimmed: number
}

export interface DiagnosticGenerationSummary {
  chunks: number
  visible_characters: number
  finish_reason: string
  stopped_by_user: boolean
}

export interface DiagnosticStateSummary {
  version_before: number
  version_after: number
  patch_applied: boolean
  applied_operations: number
  rejected_operations: number
  parser_errors: number
}

export interface DiagnosticRequestSummary {
  request_id: string
  recorded_at?: string
  started_at?: string
  session_id?: string
  character_id?: string
  user_message_id?: string | null
  assistant_message_id?: string
  provider: string
  model: string
  mock_mode: boolean
  timing: DiagnosticTiming
  prompt: DiagnosticPromptSummary
  generation: DiagnosticGenerationSummary
  state: DiagnosticStateSummary
  error?: { type: string; message: string } | null
  status: string
}


export interface CardCompatibilityDetail {
  key: string
  label: string
  status: 'supported' | 'partial' | 'isolated' | 'absent' | string
  summary: string
}

export interface CardRuntimeCheck {
  status: 'supported' | 'partial' | 'isolated' | 'absent' | string
  summary: string
  source?: string
  warnings?: string[]
}

export interface CardCompatibilityReport {
  character_id: string
  character_name: string
  version: number
  card_format: string
  card_format_version: string
  capabilities: Record<string, boolean>
  compatibility_core?: string
  details?: CardCompatibilityDetail[]
  runtime_checks?: Record<string, CardRuntimeCheck>
  counts: Record<string, number>
  native_renderers: string[]
  unknown_extensions: string[]
  ui_manifest: CardUIManifest | null
  warnings: string[]
  unsupported: string[]
  script_execution: string
}

export interface CardUIManifestPanel {
  id: string
  title?: string
  placement?: 'sidebar' | 'message.after' | string
  component: 'text' | 'tag' | 'progress' | 'stat-grid' | 'key-value' | 'character-grid' | 'inventory' | 'quest-list' | 'timeline' | string
  source: string
  max?: number
}

export interface CardUIManifest {
  schema: 'ai-tavern-ui/1' | string
  speakerStyles?: Record<string, { color?: string; avatar?: string }>
  panels?: CardUIManifestPanel[]
}

export interface Persona {
  id: string
  name: string
  description: string
  pronouns: string
  avatar_path: string
  metadata: Record<string, unknown>
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface CharacterGroup {
  id: string
  name: string
  description: string
  character_ids: string[]
  members?: Array<{ character_id: string; name: string; avatar_path: string; role: string; position: number }>
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface SessionBranch {
  id: string
  session_id: string
  title: string
  parent_message_id: string
  message_count: number
  runtime_revision: number
  created_at: string
}
