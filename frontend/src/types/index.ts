export type CharacterSecuritySeverity = 'info' | 'warning' | 'high' | 'blocked'
export type CharacterSecurityRiskLevel = 'safe' | 'notice' | 'high' | 'blocked'
export type CharacterSecurityImportMode = 'safe_copy' | 'quarantine' | 'original'

export interface CharacterSecurityFinding {
  id: string
  severity: CharacterSecuritySeverity
  category: string
  title: string
  message: string
  path: string
  evidence: string
}

export interface CharacterSecurityReport {
  format_version: number
  card_sha256: string
  risk_level: CharacterSecurityRiskLevel
  summary: string
  counts: Record<string, number>
  findings: CharacterSecurityFinding[]
  external_hosts: string[]
  has_active_content: boolean
  prompt_injection_detected: boolean
  can_import_original: boolean
  can_import_safe: boolean
  recommended_action: 'original' | 'safe_copy'
  scanner_guarantees: string[]
}

export interface CharacterCardSecurityScan {
  filename: string
  card_name: string
  report: CharacterSecurityReport
}

export interface Character {
  id: string
  name: string
  description: string
  personality: string
  scenario: string
  first_message: string
  alternate_greetings: string[]
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
  alternate_greetings: string[]
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

export interface CharacterGreetingOption {
  key: string
  kind: 'default' | 'alternate'
  label: string
  content: string
  source_index?: number | null
}


export interface CharacterStateAliasEntry {
  id: string
  alias: string
  alias_key: string
  semantic: string
  canonical_path: string
  source?: string
  confidence?: number
  created_at?: string | null
  updated_at?: string | null
}

export interface CharacterStateAliasSuggestion {
  id: string
  alias: string
  alias_key: string
  semantic: string
  canonical_path: string
  confidence: number
  observed?: boolean
  observed_paths?: string[]
  status?: string
}

export interface CharacterStateAliasTarget {
  semantic: string
  canonical_path: string
  type?: string
  source?: string
  minimum?: number | null
  maximum?: number | null
}

export interface CharacterStateAliasRegistry {
  schema: 'ai-tavern-card-aliases/1' | string
  version: number
  character_id: string
  character_name: string
  revision: string
  confirmed: CharacterStateAliasEntry[]
  suggestions: CharacterStateAliasSuggestion[]
  targets: CharacterStateAliasTarget[]
  summary: {
    confirmed_count?: number
    suggestion_count?: number
    observed_suggestion_count?: number
    semantic_target_count?: number
    [key: string]: unknown
  }
}

export interface CharacterSessionOptions {
  character_id: string
  character_name: string
  greetings: string[]
  greeting_options: CharacterGreetingOption[]
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

export interface StatusPanelField {
  label: string
  value: string
  icon?: string
}

export interface StatusPanelCharacter {
  name: string
  badge?: string
  fields?: StatusPanelField[]
}

export interface StatusPanelSection {
  kind: 'environment' | 'characters' | 'interaction' | 'atmosphere' | 'generic' | string
  title: string
  fields?: StatusPanelField[]
  characters?: StatusPanelCharacter[]
  text?: string
}

export interface StatusPanelArtifact {
  schema: 'ai-tavern-status-panel/1' | string
  protocol: 'text-end' | 'status-tag' | string
  title?: string
  sections: StatusPanelSection[]
  warnings?: string[]
  source_text?: string
}

export type MessageSegment =
  | { type: 'dialogue'; speaker: string; text: string; emotion?: string }
  | { type: 'narration' | 'thought' | 'markdown'; text: string }
  | { type: 'action'; speaker?: string; text: string }
  | { type: 'card-state-placeholder' }
  | { type: 'status-panel-placeholder'; artifact_index: number }

export interface MessageArtifact {
  type: 'dice' | 'battle-check' | 'battle-map' | 'state-diff' | 'status-panel' | 'generic'
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

export interface MessagePage {
  items: Message[]
  has_more: boolean
  oldest_sequence: number | null
  newest_sequence: number | null
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
  auto_state_update_recovery: boolean
  api_key_configured: boolean
  api_key_masked: string
  api_key_storage: 'windows_dpapi' | 'environment' | 'database_legacy'
  api_key_error: string
  custom_headers: Record<string, string>
  settings_writable: boolean
  diagnostics_enabled: boolean
  selftest_enabled: boolean
}

export interface BackupDataSummary {
  database_path: string
  exists: boolean
  revision: string | null
  counts: Record<string, number>
  integrity: string
}

export interface PendingRestoreStatus {
  restore_id: string
  staged_at: string
  backup_created_at: string
  source_app_version: string
  alembic_revision: string
  counts: Record<string, number>
  asset_count: number
  restart_required: boolean
}

export interface BackupStatus {
  format_version: number
  current: BackupDataSummary
  pending_restore: PendingRestoreStatus | null
  portable_backup_excludes: string[]
}

export interface BackupRestoreResult extends PendingRestoreStatus {
  success: boolean
  message: string
}

export type RuntimeMode = 'relationship' | 'adventure' | 'general'


export interface RuntimeStateSchemaField {
  path: string
  type: string
  declared?: boolean
  source?: string
  mutable?: boolean
  required?: boolean
  description?: string
  semantic?: string
  canonical_path?: string
  semantic_role?: 'source' | 'projection' | string
  derived?: boolean
  minimum?: number
  maximum?: number
  items_type?: string
  update_modes?: string[]
  [key: string]: unknown
}

export interface RuntimeStateSchema {
  schema: 'ai-tavern-state-schema/1' | string
  version: number
  source?: string
  fields: Record<string, RuntimeStateSchemaField>
  containers: Record<string, Record<string, unknown>>
  semantic_index?: Record<string, { canonical_path?: string; paths?: string[]; source?: string; [key: string]: unknown }>
  summary: {
    field_count?: number
    declared_count?: number
    numeric_count?: number
    constrained_count?: number
    semantic_count?: number
    strict_container_count?: number
    [key: string]: unknown
  }
}

export interface RuntimeSchemaValidation {
  valid: boolean
  errors: Array<{ path?: string; code?: string; message?: string; [key: string]: unknown }>
  warnings: Array<{ path?: string; code?: string; message?: string; [key: string]: unknown }>
  error_count: number
  warning_count: number
}

export interface RuntimeProfile {
  version: number
  mode: RuntimeMode
  card_spec: string
  card_spec_version: string
  capabilities: Record<string, boolean>
  native_renderers: string[]
  script_execution: 'disabled' | 'safe-native-emulation'
  regex_script_count: number
  lorebook_entry_count: number
  external_resource_count: number
  recommended_context_window?: number
  emulation?: {
    version?: number
    mode?: string
    status_panel?: { enabled?: boolean; theme?: string; memory_page_size?: number; sections?: string[] }
    prompt_filters?: Record<string, boolean>
    native_actions?: Array<{ id: string; label: string; status: string }>
  }
  state_policy?: Record<string, unknown>
  state_schema?: RuntimeStateSchema
  state_schema_summary?: RuntimeStateSchema['summary']
  state_aliases?: CharacterStateAliasRegistry
  state_alias_summary?: CharacterStateAliasRegistry['summary']
  warnings: string[]
}

export interface SceneRuntimeState {
  location?: string
  date?: string
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

export interface RuntimeDecisionTraceField {
  path?: string
  namespace?: string
  classification?: 'existing' | 'created' | 'unresolved' | string
  existed_before?: boolean
  exists_after?: boolean
  declared?: boolean
  schema_type?: string
  semantic?: string
  schema_source?: string
  mutable?: boolean
  minimum?: number
  maximum?: number
  update_modes?: string[]
  [key: string]: unknown
}

export interface RuntimeDecisionStage {
  decision?: string
  reason_code?: string
  reason?: string
  before_exists?: boolean
  before?: unknown
  after_exists?: boolean
  after?: unknown
  changed?: boolean
  input_operation?: Record<string, unknown>
  output_operation?: Record<string, unknown>
  [key: string]: unknown
}

export interface RuntimeDecisionTrace {
  operation_id?: string
  source?: string
  outcome?: string
  raw_operation?: Record<string, unknown> | unknown
  normalized_operation?: Record<string, unknown> | unknown
  field?: RuntimeDecisionTraceField
  alias?: RuntimeDecisionStage
  policy?: RuntimeDecisionStage
  schema?: RuntimeDecisionStage
  apply?: RuntimeDecisionStage
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
  decision_trace: RuntimeDecisionTrace[]
  created_at: string | null
}

export interface RuntimeSession {
  session_id: string
  profile: RuntimeProfile
  initial_state: RuntimeState
  state: RuntimeState
  schema_validation?: RuntimeSchemaValidation
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

export interface PromptBudgetSummary {
  context_window: number
  reserved_output_tokens: number
  input_budget: number
  estimated_input_tokens: number
  remaining_tokens: number
  usage_percent: number
}

export interface PromptSectionInspection {
  key: string
  name: string
  budget_tokens: number
  estimated_tokens: number
  included: boolean
  truncated: boolean
  reason: string
  source: string
}

export interface PromptMemoryInspection {
  id: string
  category: string
  scope: 'global' | 'character' | 'session' | string
  content: string
  importance: number
  enabled: boolean
  selected: boolean
  included: boolean
  truncated: boolean
  estimated_tokens: number
  reason: string
}

export interface PromptLorebookInspection {
  id: string
  title: string
  kind: 'character_core' | 'runtime_protocol' | 'world' | string
  enabled: boolean
  constant: boolean
  probability: number
  keys: string[]
  matched_keys: string[]
  secondary_matched_keys: string[]
  triggered: boolean
  selected: boolean
  included: boolean
  truncated: boolean
  content: string
  resolved_content: string
  injected_content: string
  content_characters: number
  resolved_characters: number
  injected_characters: number
  estimated_tokens: number
  reason: string
}

export interface PromptHistoryInspection {
  total_messages: number
  included_messages: number
  trimmed_messages: number
  earliest_included_sequence: number | null
  budget_tokens: number
  estimated_tokens: number
}

export interface PromptInspection {
  summary: PromptBudgetSummary
  sections: PromptSectionInspection[]
  memories: PromptMemoryInspection[]
  lorebook: PromptLorebookInspection[]
  history: PromptHistoryInspection
}

export interface PromptPreview {
  sections: PromptSection[]
  total_estimated_tokens: number
  context_budget: number
  section_content_complete?: boolean
  inspection?: PromptInspection | null
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
