import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  Loader2,
  MessageSquarePlus,
  Sparkles,
  UserRound,
  Users,
  X,
} from 'lucide-react'
import { getCharacterSessionOptions, getGroups, getPersonas } from '@/api'
import { getErrorMessage } from '@/lib/errors'
import type {
  Character,
  CharacterGroup,
  CharacterSessionOptions,
  Persona,
  RuntimeState,
  SessionCreateOptions,
} from '@/types'

interface NewSessionWizardProps {
  open: boolean
  characters: Character[]
  initialCharacterId?: string | null
  initialGroupId?: string | null
  onClose: () => void
  onCreate: (characterId: string, options: SessionCreateOptions) => Promise<void>
}

type ConversationMode = 'single' | 'group'
type PersonaChoice = 'default' | 'none' | string

const stepLabels = ['参与者', '身份与标题', '开场与状态']

const defaultTitle = (
  mode: ConversationMode,
  character: Character | undefined,
  group: CharacterGroup | undefined,
) => mode === 'group' && group ? group.name : character ? `与${character.name}的对话` : '新对话'

export default function NewSessionWizard({
  open,
  characters,
  initialCharacterId,
  initialGroupId,
  onClose,
  onCreate,
}: NewSessionWizardProps) {
  const [step, setStep] = useState(0)
  const [mode, setMode] = useState<ConversationMode>('single')
  const [characterId, setCharacterId] = useState('')
  const [groupId, setGroupId] = useState('')
  const [personas, setPersonas] = useState<Persona[]>([])
  const [groups, setGroups] = useState<CharacterGroup[]>([])
  const [personaChoice, setPersonaChoice] = useState<PersonaChoice>('default')
  const [title, setTitle] = useState('新对话')
  const [titleTouched, setTitleTouched] = useState(false)
  const [sessionOptions, setSessionOptions] = useState<CharacterSessionOptions | null>(null)
  const [greetingChoice, setGreetingChoice] = useState('0')
  const [customizeInitialState, setCustomizeInitialState] = useState(false)
  const [initialStateText, setInitialStateText] = useState('{}')
  const [loadingLists, setLoadingLists] = useState(false)
  const [loadingOptions, setLoadingOptions] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const selectedGroup = groups.find((group) => group.id === groupId)
  const eligibleCharacters = useMemo(() => {
    if (mode !== 'group' || !selectedGroup) return characters
    const allowed = new Set(selectedGroup.character_ids)
    return characters.filter((character) => allowed.has(character.id))
  }, [characters, mode, selectedGroup])
  const selectedCharacter = characters.find((character) => character.id === characterId)
  const defaultPersona = personas.find((persona) => persona.is_default)

  useEffect(() => {
    if (!open) return
    let active = true
    setStep(0)
    setError('')
    setSubmitting(false)
    setTitleTouched(false)
    setCustomizeInitialState(false)
    setSessionOptions(null)
    setGreetingChoice('0')
    setLoadingLists(true)

    Promise.all([getPersonas(), getGroups()])
      .then(([personaResponse, groupResponse]) => {
        if (!active) return
        const nextPersonas = personaResponse.data
        const nextGroups = groupResponse.data
        setPersonas(nextPersonas)
        setGroups(nextGroups)
        setPersonaChoice('default')

        const requestedGroup = initialGroupId
          ? nextGroups.find((group) => group.id === initialGroupId)
          : undefined
        const nextMode: ConversationMode = requestedGroup ? 'group' : 'single'
        const requestedCharacter = characters.find((character) => character.id === initialCharacterId)
        const nextCharacterId = requestedGroup
          ? requestedGroup.character_ids.find((id) => characters.some((character) => character.id === id)) || ''
          : requestedCharacter?.id || characters[0]?.id || ''

        setMode(nextMode)
        setGroupId(requestedGroup?.id || '')
        setCharacterId(nextCharacterId)
        setTitle(defaultTitle(nextMode, characters.find((item) => item.id === nextCharacterId), requestedGroup))
      })
      .catch((reason) => {
        if (active) setError(getErrorMessage(reason, '会话选项加载失败'))
      })
      .finally(() => {
        if (active) setLoadingLists(false)
      })

    return () => { active = false }
  }, [open, initialCharacterId, initialGroupId, characters])

  useEffect(() => {
    if (!open || !characterId) return
    let active = true
    setLoadingOptions(true)
    setError('')
    getCharacterSessionOptions(characterId)
      .then((response) => {
        if (!active) return
        setSessionOptions(response.data)
        setGreetingChoice(response.data.greetings.length ? '0' : 'none')
        setInitialStateText(JSON.stringify(response.data.initial_state, null, 2))
        setCustomizeInitialState(false)
      })
      .catch((reason) => {
        if (active) {
          setSessionOptions(null)
          setError(getErrorMessage(reason, '角色开场信息加载失败'))
        }
      })
      .finally(() => {
        if (active) setLoadingOptions(false)
      })
    return () => { active = false }
  }, [open, characterId])

  useEffect(() => {
    if (!open || mode !== 'group' || !selectedGroup) return
    if (!selectedGroup.character_ids.includes(characterId)) {
      setCharacterId(selectedGroup.character_ids.find((id) => characters.some((item) => item.id === id)) || '')
    }
  }, [open, mode, selectedGroup, characterId, characters])

  useEffect(() => {
    if (!open || titleTouched) return
    setTitle(defaultTitle(mode, selectedCharacter, selectedGroup))
  }, [open, mode, selectedCharacter, selectedGroup, titleTouched])

  if (!open) return null

  const selectMode = (nextMode: ConversationMode) => {
    setMode(nextMode)
    setError('')
    if (nextMode === 'group') {
      const nextGroup = selectedGroup || groups[0]
      setGroupId(nextGroup?.id || '')
      const nextCharacter = nextGroup?.character_ids.find((id) => characters.some((item) => item.id === id))
      if (nextCharacter) setCharacterId(nextCharacter)
    } else if (!characters.some((item) => item.id === characterId)) {
      setCharacterId(characters[0]?.id || '')
    }
  }

  const validateStep = () => {
    if (step === 0) {
      if (mode === 'group' && !selectedGroup) return '请选择一个角色编组'
      if (!selectedCharacter) return '请选择主角色'
    }
    if (step === 1 && !title.trim()) return '请输入会话标题'
    if (step === 2) {
      if (loadingOptions || !sessionOptions) return '角色开场信息尚未加载完成'
      if (customizeInitialState) {
        try {
          const parsed = JSON.parse(initialStateText)
          if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') return '初始状态的根节点必须是 JSON 对象'
        } catch {
          return '初始状态不是有效的 JSON'
        }
      }
    }
    return ''
  }

  const goNext = () => {
    const issue = validateStep()
    if (issue) {
      setError(issue)
      return
    }
    setError('')
    setStep((current) => Math.min(stepLabels.length - 1, current + 1))
  }

  const submit = async () => {
    const issue = validateStep()
    if (issue || !selectedCharacter || !sessionOptions) {
      setError(issue || '会话选项不完整')
      return
    }

    let initialState: RuntimeState | undefined
    if (customizeInitialState) initialState = JSON.parse(initialStateText) as RuntimeState

    const options: SessionCreateOptions = {
      title: title.trim(),
      group_id: mode === 'group' ? selectedGroup?.id : undefined,
      use_default_persona: personaChoice === 'default',
      persona_id: personaChoice !== 'default' && personaChoice !== 'none' ? personaChoice : undefined,
      skip_opening_message: greetingChoice === 'none',
      opening_message: greetingChoice === 'none'
        ? undefined
        : sessionOptions.greetings[Number(greetingChoice)],
      initial_state: initialState,
    }

    setSubmitting(true)
    setError('')
    try {
      await onCreate(selectedCharacter.id, options)
    } catch (reason) {
      setError(getErrorMessage(reason, '会话创建失败'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="manager-scrim" role="presentation">
      <section className="manager-modal session-wizard" role="dialog" aria-modal="true" aria-labelledby="new-session-title">
        <header>
          <div><MessageSquarePlus size={18}/><span id="new-session-title">新建会话</span></div>
          <button type="button" onClick={onClose} aria-label="关闭新会话向导"><X size={18}/></button>
        </header>

        <div className="session-wizard__steps" aria-label="新会话步骤">
          {stepLabels.map((label, index) => (
            <div key={label} className={index === step ? 'is-current' : index < step ? 'is-complete' : ''}>
              <span>{index < step ? <Check size={12}/> : index + 1}</span>
              <small>{label}</small>
            </div>
          ))}
        </div>

        <div className="manager-body session-wizard__body">
          {loadingLists ? (
            <div className="manager-empty"><Loader2 className="animate-spin mx-auto mb-2" size={20}/>正在加载角色、Persona 与编组…</div>
          ) : null}

          {!loadingLists && step === 0 ? (
            <div className="session-wizard__section">
              <div className="session-wizard__mode-grid">
                <button type="button" className={mode === 'single' ? 'is-selected' : ''} onClick={() => selectMode('single')}>
                  <UserRound size={18}/><strong>单角色对话</strong><small>与一个角色开始独立剧情</small>
                </button>
                <button type="button" className={mode === 'group' ? 'is-selected' : ''} onClick={() => selectMode('group')} disabled={!groups.length}>
                  <Users size={18}/><strong>多角色编组</strong><small>{groups.length ? '使用已有编组开始群像剧情' : '请先创建角色编组'}</small>
                </button>
              </div>

              {mode === 'group' ? (
                <label className="session-wizard__field">
                  <span>角色编组</span>
                  <select className="input" value={groupId} onChange={(event) => setGroupId(event.target.value)}>
                    <option value="">请选择编组</option>
                    {groups.map((group) => <option key={group.id} value={group.id}>{group.name}（{group.character_ids.length} 人）</option>)}
                  </select>
                </label>
              ) : null}

              <label className="session-wizard__field">
                <span>{mode === 'group' ? '主角色' : '角色'}</span>
                <select className="input" value={characterId} onChange={(event) => setCharacterId(event.target.value)}>
                  <option value="">请选择角色</option>
                  {eligibleCharacters.map((character) => <option key={character.id} value={character.id}>{character.name}</option>)}
                </select>
                {mode === 'group' ? <small>主角色决定角色卡、初始状态和默认开场白；编组成员会共同参与 Prompt。</small> : null}
              </label>

              {selectedCharacter ? (
                <div className="session-wizard__character-preview">
                  <div>{selectedCharacter.avatar_path ? <img src={selectedCharacter.avatar_path} alt=""/> : selectedCharacter.name.slice(0, 1)}</div>
                  <span><strong>{selectedCharacter.name}</strong><small>{selectedCharacter.description || selectedCharacter.scenario || '尚未填写角色简介'}</small></span>
                </div>
              ) : null}
            </div>
          ) : null}

          {!loadingLists && step === 1 ? (
            <div className="session-wizard__section">
              <label className="session-wizard__field">
                <span>会话标题</span>
                <input
                  className="input"
                  value={title}
                  maxLength={200}
                  onChange={(event) => { setTitle(event.target.value); setTitleTouched(true) }}
                  placeholder="例如：钟楼下的第一次见面"
                  autoFocus
                />
                <small>{title.length}/200</small>
              </label>

              <label className="session-wizard__field">
                <span>玩家 Persona</span>
                <select className="input" value={personaChoice} onChange={(event) => setPersonaChoice(event.target.value)}>
                  <option value="default">使用默认 Persona{defaultPersona ? `（${defaultPersona.name}）` : '（当前未设置）'}</option>
                  <option value="none">不绑定 Persona</option>
                  {personas.map((persona) => <option key={persona.id} value={persona.id}>{persona.name}{persona.is_default ? ' · 默认' : ''}</option>)}
                </select>
                <small>Persona 会作为玩家身份加入 Prompt；不绑定时使用设置中的用户名。</small>
              </label>

              <div className="session-wizard__summary-card">
                <Sparkles size={16}/>
                <div>
                  <strong>{mode === 'group' ? selectedGroup?.name : selectedCharacter?.name}</strong>
                  <p>{personaChoice === 'none' ? '不绑定 Persona' : personaChoice === 'default' ? `默认 Persona：${defaultPersona?.name || '未设置'}` : `Persona：${personas.find((item) => item.id === personaChoice)?.name || '未选择'}`}</p>
                </div>
              </div>
            </div>
          ) : null}

          {!loadingLists && step === 2 ? (
            <div className="session-wizard__section">
              <div>
                <div className="session-wizard__field-heading"><span>开场白</span><small>选择角色进入会话时显示的第一条消息</small></div>
                {loadingOptions ? <div className="manager-empty"><Loader2 className="animate-spin mx-auto mb-2" size={20}/>正在生成会话预览…</div> : null}
                {!loadingOptions && sessionOptions ? (
                  <div className="session-wizard__greetings">
                    {sessionOptions.greetings.map((greeting, index) => (
                      <label key={`${index}-${greeting.slice(0, 20)}`} className={greetingChoice === String(index) ? 'is-selected' : ''}>
                        <input type="radio" name="opening-message" value={index} checked={greetingChoice === String(index)} onChange={(event) => setGreetingChoice(event.target.value)}/>
                        <span><strong>{index === 0 ? '默认开场白' : `备用开场白 ${index}`}</strong><p>{greeting}</p></span>
                      </label>
                    ))}
                    <label className={greetingChoice === 'none' ? 'is-selected' : ''}>
                      <input type="radio" name="opening-message" value="none" checked={greetingChoice === 'none'} onChange={(event) => setGreetingChoice(event.target.value)}/>
                      <span><strong>空白开始</strong><p>不插入角色开场白，直接进入空会话。</p></span>
                    </label>
                  </div>
                ) : null}
              </div>

              <details className="session-wizard__advanced">
                <summary><ChevronDown size={15}/><span>高级：初始运行时状态</span></summary>
                <div>
                  <label className="toggle-label">
                    <input type="checkbox" checked={customizeInitialState} onChange={(event) => setCustomizeInitialState(event.target.checked)}/>
                    自定义本会话的初始状态
                  </label>
                  <p>默认状态由角色卡和运行时兼容层自动生成。仅在明确了解 JSON 结构时修改。</p>
                  <textarea
                    className="textarea session-wizard__state-editor"
                    value={initialStateText}
                    onChange={(event) => setInitialStateText(event.target.value)}
                    disabled={!customizeInitialState}
                    spellCheck={false}
                    aria-label="初始运行时状态 JSON"
                  />
                </div>
              </details>
            </div>
          ) : null}

          {error ? <p className="form-error session-wizard__error" role="alert">{error}</p> : null}
        </div>

        <footer className="session-wizard__footer">
          <button type="button" className="btn" onClick={step === 0 ? onClose : () => { setStep((current) => current - 1); setError('') }} disabled={submitting}>
            {step === 0 ? '取消' : <><ArrowLeft size={14}/>上一步</>}
          </button>
          {step < stepLabels.length - 1 ? (
            <button type="button" className="btn btn-primary" onClick={goNext} disabled={loadingLists}>
              下一步<ArrowRight size={14}/>
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => void submit()} disabled={submitting || loadingOptions || !sessionOptions}>
              {submitting ? <Loader2 size={14} className="animate-spin"/> : <MessageSquarePlus size={14}/>}
              创建会话
            </button>
          )}
        </footer>
      </section>
    </div>
  )
}
