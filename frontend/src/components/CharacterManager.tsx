import { useEffect, useMemo, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  Eye,
  MessageSquareQuote,
  Plus,
  Save,
  Sparkles,
  Trash2,
  UserRound,
  X,
} from 'lucide-react'
import { getLorebook, updateLorebook } from '@/api'
import { useAppStore } from '@/stores/appStore'
import type { Character, CharacterDraft, LorebookEntry } from '@/types'
import { getErrorMessage } from '@/lib/errors'
import { useToast } from './ui/ToastProvider'

interface CharacterManagerProps {
  open: boolean
  mode: 'create' | 'edit'
  character: Character | null
  onClose: () => void
  onSaved: (character: Character) => void
}

type CharacterTab = 'basic' | 'greetings' | 'lorebook'
type GreetingPreview = 'default' | number

const emptyDraft: CharacterDraft = {
  name: '',
  description: '',
  personality: '',
  scenario: '',
  first_message: '',
  alternate_greetings: [],
}

const createLorebookEntry = (order: number): LorebookEntry => ({
  keys: [],
  secondary_keys: [],
  comment: '',
  content: '',
  constant: false,
  selective: false,
  enabled: true,
  insertion_order: order,
  position: 'before_char',
  use_regex: false,
  probability: 100,
  extensions: {},
})

const characterToDraft = (character: Character | null): CharacterDraft => character ? {
  name: character.name,
  description: character.description || '',
  personality: character.personality || '',
  scenario: character.scenario || '',
  first_message: character.first_message || '',
  alternate_greetings: [...(character.alternate_greetings || [])],
} : { ...emptyDraft, alternate_greetings: [] }

const validateGreetingDraft = (draft: CharacterDraft) => {
  const seen = new Set<string>()
  const firstMessage = draft.first_message.trim()
  if (firstMessage) seen.add(firstMessage)

  for (let index = 0; index < draft.alternate_greetings.length; index += 1) {
    const greeting = draft.alternate_greetings[index].trim()
    if (!greeting) return `备用开场白 ${index + 1} 不能为空`
    if (seen.has(greeting)) return `开场白内容重复：备用开场白 ${index + 1}`
    seen.add(greeting)
  }
  return ''
}

export default function CharacterManager({ open, mode, character, onClose, onSaved }: CharacterManagerProps) {
  const createCharacter = useAppStore((state) => state.createCharacter)
  const updateCharacter = useAppStore((state) => state.updateCharacter)
  const { showToast } = useToast()
  const [draft, setDraft] = useState<CharacterDraft>(emptyDraft)
  const [activeTab, setActiveTab] = useState<CharacterTab>('basic')
  const [saving, setSaving] = useState(false)
  const [fieldError, setFieldError] = useState('')
  const [greetingError, setGreetingError] = useState('')
  const [previewChoice, setPreviewChoice] = useState<GreetingPreview>('default')
  const [previewExpanded, setPreviewExpanded] = useState(false)
  const [lorebookEntries, setLorebookEntries] = useState<LorebookEntry[]>([])
  const [lorebookLoadedFor, setLorebookLoadedFor] = useState<string | null>(null)
  const [loadingLorebook, setLoadingLorebook] = useState(false)
  const [savingLorebook, setSavingLorebook] = useState(false)

  useEffect(() => {
    if (!open) return
    setDraft(characterToDraft(character))
    setActiveTab('basic')
    setFieldError('')
    setGreetingError('')
    setPreviewChoice('default')
    setPreviewExpanded(false)
    setLorebookEntries([])
    setLorebookLoadedFor(null)
  }, [open, character?.id, mode])

  useEffect(() => {
    if (!open || activeTab !== 'lorebook' || !character || lorebookLoadedFor === character.id) return
    let cancelled = false
    setLoadingLorebook(true)
    void getLorebook(character.id)
      .then((response) => {
        if (cancelled) return
        setLorebookEntries(response.data.entries)
        setLoadingLorebook(false)
        setLorebookLoadedFor(character.id)
      })
      .catch((error) => {
        if (cancelled) return
        setLoadingLorebook(false)
        showToast(getErrorMessage(error, '世界书加载失败'), 'error')
      })
    return () => { cancelled = true }
  }, [activeTab, character, lorebookLoadedFor, open, showToast])

  const title = mode === 'create' ? '新建角色' : `编辑角色：${character?.name || ''}`
  const canEditLorebook = mode === 'edit' && Boolean(character)
  const dirtyName = draft.name.trim()
  const entryCountLabel = useMemo(() => `${lorebookEntries.length} 条`, [lorebookEntries.length])
  const greetingCountLabel = `${draft.alternate_greetings.length + (draft.first_message.trim() ? 1 : 0)} 条`
  const previewText = previewChoice === 'default'
    ? draft.first_message
    : draft.alternate_greetings[previewChoice] || ''
  const previewLabel = previewChoice === 'default' ? '默认开场白' : `备用开场白 ${previewChoice + 1}`
  const previewIsLong = previewText.length > 280 || previewText.split('\n').length > 8

  if (!open) return null

  const updateDraft = (field: Exclude<keyof CharacterDraft, 'alternate_greetings'>, value: string) => {
    setDraft((current) => ({ ...current, [field]: value }))
    if (field === 'name' && value.trim()) setFieldError('')
    if (field === 'first_message') setGreetingError('')
  }

  const updateAlternateGreeting = (index: number, value: string) => {
    setDraft((current) => ({
      ...current,
      alternate_greetings: current.alternate_greetings.map((item, itemIndex) => itemIndex === index ? value : item),
    }))
    setGreetingError('')
  }

  const addAlternateGreeting = () => {
    setDraft((current) => ({ ...current, alternate_greetings: [...current.alternate_greetings, ''] }))
    setPreviewChoice(draft.alternate_greetings.length)
    setPreviewExpanded(false)
    setGreetingError('')
  }

  const removeAlternateGreeting = (index: number) => {
    setDraft((current) => ({
      ...current,
      alternate_greetings: current.alternate_greetings.filter((_, itemIndex) => itemIndex !== index),
    }))
    if (previewChoice === index) setPreviewChoice('default')
    else if (typeof previewChoice === 'number' && previewChoice > index) setPreviewChoice(previewChoice - 1)
    setGreetingError('')
  }

  const moveAlternateGreeting = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= draft.alternate_greetings.length) return
    setDraft((current) => {
      const next = [...current.alternate_greetings]
      ;[next[index], next[target]] = [next[target], next[index]]
      return { ...current, alternate_greetings: next }
    })
    if (previewChoice === index) setPreviewChoice(target)
    else if (previewChoice === target) setPreviewChoice(index)
  }

  const saveBasic = async () => {
    if (!dirtyName) {
      setFieldError('请输入角色名称')
      setActiveTab('basic')
      return
    }
    const greetingIssue = validateGreetingDraft(draft)
    if (greetingIssue) {
      setGreetingError(greetingIssue)
      setActiveTab('greetings')
      return
    }

    setSaving(true)
    setFieldError('')
    setGreetingError('')
    try {
      const payload: CharacterDraft = {
        ...draft,
        name: dirtyName,
        first_message: draft.first_message.trim(),
        alternate_greetings: draft.alternate_greetings.map((item) => item.trim()),
      }
      const saved = mode === 'create'
        ? await createCharacter(payload)
        : await updateCharacter(character!.id, payload)
      showToast(mode === 'create' ? '角色已创建' : '角色资料与开场白已保存', 'success')
      onSaved(saved)
      if (mode === 'create') onClose()
      else setDraft(characterToDraft(saved))
    } catch (error) {
      showToast(getErrorMessage(error, '角色保存失败'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const updateEntry = <K extends keyof LorebookEntry>(index: number, field: K, value: LorebookEntry[K]) => {
    setLorebookEntries((current) => current.map((entry, entryIndex) => (
      entryIndex === index ? { ...entry, [field]: value } : entry
    )))
  }

  const removeEntry = (index: number) => {
    setLorebookEntries((current) => current
      .filter((_, entryIndex) => entryIndex !== index)
      .map((entry, entryIndex) => ({ ...entry, insertion_order: entryIndex })))
  }

  const saveLorebook = async () => {
    if (!character) return
    setSavingLorebook(true)
    try {
      const normalized = lorebookEntries.map((entry, index) => ({
        ...entry,
        keys: entry.keys.map((item) => item.trim()).filter(Boolean),
        secondary_keys: entry.secondary_keys.map((item) => item.trim()).filter(Boolean),
        insertion_order: index,
        probability: Math.min(100, Math.max(0, Number(entry.probability) || 0)),
      }))
      const response = await updateLorebook(character.id, { entries: normalized })
      setLorebookEntries(response.data.entries)
      showToast('世界书已保存', 'success')
    } catch (error) {
      showToast(getErrorMessage(error, '世界书保存失败'), 'error')
    } finally {
      setSavingLorebook(false)
    }
  }

  return (
    <div className="manager-scrim" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !saving && !savingLorebook) onClose()
    }}>
      <section className="manager-modal character-manager" role="dialog" aria-modal="true" aria-labelledby="character-manager-title">
        <header>
          <div><UserRound size={18}/><span id="character-manager-title">{title}</span></div>
          <button type="button" aria-label="关闭角色编辑器" disabled={saving || savingLorebook} onClick={onClose}><X size={18}/></button>
        </header>

        <div className="character-manager__tabs" role="tablist" aria-label="角色编辑区域">
          <button type="button" role="tab" aria-selected={activeTab === 'basic'} className={activeTab === 'basic' ? 'is-active' : ''} onClick={() => setActiveTab('basic')}>
            <Sparkles size={15}/>基础资料
          </button>
          <button type="button" role="tab" aria-selected={activeTab === 'greetings'} className={activeTab === 'greetings' ? 'is-active' : ''} onClick={() => setActiveTab('greetings')}>
            <MessageSquareQuote size={15}/>开场白 <span>{greetingCountLabel}</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'lorebook'}
            disabled={!canEditLorebook}
            className={activeTab === 'lorebook' ? 'is-active' : ''}
            title={canEditLorebook ? '编辑角色世界书' : '先创建角色，再编辑世界书'}
            onClick={() => setActiveTab('lorebook')}
          ><BookOpen size={15}/>世界书 <span>{entryCountLabel}</span></button>
        </div>

        <div className="manager-body">
          {activeTab === 'basic' ? (
            <form className="character-form" onSubmit={(event) => { event.preventDefault(); void saveBasic() }}>
              <label>
                <span>角色名称 *</span>
                <input
                  autoFocus
                  className={`input ${fieldError ? 'input-error' : ''}`}
                  value={draft.name}
                  maxLength={200}
                  onChange={(event) => updateDraft('name', event.target.value)}
                  placeholder="例如：林雅"
                />
                {fieldError ? <small className="form-error">{fieldError}</small> : null}
              </label>
              <label><span>角色描述</span><textarea className="textarea" rows={4} value={draft.description} onChange={(event) => updateDraft('description', event.target.value)} placeholder="外貌、身份、背景设定…"/></label>
              <label><span>性格</span><textarea className="textarea" rows={3} value={draft.personality} onChange={(event) => updateDraft('personality', event.target.value)} placeholder="性格特征、说话习惯、价值观…"/></label>
              <label><span>场景</span><textarea className="textarea" rows={3} value={draft.scenario} onChange={(event) => updateDraft('scenario', event.target.value)} placeholder="故事发生的地点和当前情境…"/></label>
              <p className="character-form__hint">默认与备用开场白已移到“开场白”标签，可独立预览和排序。</p>
            </form>
          ) : null}

          {activeTab === 'greetings' ? (
            <form className="greeting-editor" onSubmit={(event) => { event.preventDefault(); void saveBasic() }}>
              <div className="greeting-editor__intro">
                <div><strong>会话开场白</strong><p>默认开场白与备用开场白会同步出现在新会话向导中。</p></div>
                <button type="button" className="btn btn-secondary btn-sm" disabled={draft.alternate_greetings.length >= 50} onClick={addAlternateGreeting}><Plus size={14}/>添加备用开场白</button>
              </div>

              <section className="greeting-editor__default">
                <div className="greeting-editor__section-heading">
                  <div><strong>默认开场白</strong><small>可以留空；留空时向导仍可选择空白开始。</small></div>
                  <button type="button" className={previewChoice === 'default' ? 'is-active' : ''} onClick={() => { setPreviewChoice('default'); setPreviewExpanded(false) }}><Eye size={14}/>预览</button>
                </div>
                <textarea aria-label="默认开场白" className="textarea" rows={5} value={draft.first_message} onChange={(event) => updateDraft('first_message', event.target.value)} placeholder="角色在新会话中的第一句话…"/>
              </section>

              <div className="greeting-editor__list">
                {draft.alternate_greetings.length === 0 ? <p className="manager-empty">暂无备用开场白。添加后，用户可在新会话向导中选择不同开局。</p> : null}
                {draft.alternate_greetings.map((greeting, index) => (
                  <article className="greeting-editor__card" key={`alternate-${index}`}>
                    <div className="greeting-editor__card-header">
                      <strong>备用开场白 {index + 1}</strong>
                      <div>
                        <button type="button" aria-label={`预览备用开场白 ${index + 1}`} className={previewChoice === index ? 'is-active' : ''} onClick={() => { setPreviewChoice(index); setPreviewExpanded(false) }}><Eye size={14}/></button>
                        <button type="button" aria-label={`上移备用开场白 ${index + 1}`} disabled={index === 0} onClick={() => moveAlternateGreeting(index, -1)}><ArrowUp size={14}/></button>
                        <button type="button" aria-label={`下移备用开场白 ${index + 1}`} disabled={index === draft.alternate_greetings.length - 1} onClick={() => moveAlternateGreeting(index, 1)}><ArrowDown size={14}/></button>
                        <button type="button" aria-label={`删除备用开场白 ${index + 1}`} onClick={() => removeAlternateGreeting(index)}><Trash2 size={14}/></button>
                      </div>
                    </div>
                    <textarea aria-label={`备用开场白 ${index + 1}`} className="textarea" rows={5} value={greeting} onChange={(event) => updateAlternateGreeting(index, event.target.value)} placeholder="输入另一种开场方式…"/>
                    <small>{greeting.length.toLocaleString()} 字符</small>
                  </article>
                ))}
              </div>

              {greetingError ? <p className="form-error" role="alert">{greetingError}</p> : null}

              <section className="greeting-preview" aria-live="polite">
                <div className="greeting-preview__header">
                  <span><Eye size={15}/><strong>实时预览 · {previewLabel}</strong></span>
                  {previewIsLong ? <button type="button" onClick={() => setPreviewExpanded((value) => !value)}>{previewExpanded ? '收起' : '展开全文'}</button> : null}
                </div>
                {previewText.trim() ? <p className={previewExpanded ? 'is-expanded' : ''}>{previewText}</p> : <p className="is-empty">当前开场白为空。</p>}
              </section>

            </form>
          ) : null}

          {activeTab === 'lorebook' ? (
            <div className="lorebook-editor">
              <div className="lorebook-editor__toolbar">
                <div><strong>世界书条目</strong><p>关键词命中后，内容会注入角色上下文。</p></div>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setLorebookEntries((current) => [...current, createLorebookEntry(current.length)])}><Plus size={14}/>添加条目</button>
              </div>

              {loadingLorebook ? <p className="manager-empty">正在加载世界书…</p> : null}
              {!loadingLorebook && lorebookEntries.length === 0 ? <p className="manager-empty">暂无世界书条目，可以从右上角添加。</p> : null}

              <div className="lorebook-entry-list">
                {lorebookEntries.map((entry, index) => (
                  <article key={`${entry.id ?? 'new'}-${index}`} className="lorebook-entry-card">
                    <div className="lorebook-entry-card__header">
                      <strong>{entry.comment.trim() || `条目 ${index + 1}`}</strong>
                      <div>
                        <label className="toggle-label"><input type="checkbox" checked={entry.enabled} onChange={(event) => updateEntry(index, 'enabled', event.target.checked)}/><span>启用</span></label>
                        <button type="button" aria-label={`删除世界书条目 ${index + 1}`} onClick={() => removeEntry(index)}><Trash2 size={15}/></button>
                      </div>
                    </div>
                    <div className="lorebook-entry-grid">
                      <label><span>标题 / 备注</span><input className="input" value={entry.comment} onChange={(event) => updateEntry(index, 'comment', event.target.value)} placeholder="例如：古老图书馆"/></label>
                      <label><span>触发关键词</span><input className="input" value={entry.keys.join(', ')} onChange={(event) => updateEntry(index, 'keys', event.target.value.split(/[,，]/).map((item) => item.trimStart()))} placeholder="魔法, 图书馆"/></label>
                      <label className="lorebook-entry-grid__wide"><span>注入内容</span><textarea className="textarea" rows={4} value={entry.content} onChange={(event) => updateEntry(index, 'content', event.target.value)} placeholder="模型在关键词命中后需要知道的设定…"/></label>
                      <label><span>触发概率（0-100）</span><input className="input" type="number" min={0} max={100} value={entry.probability} onChange={(event) => updateEntry(index, 'probability', Number(event.target.value))}/></label>
                      <div className="lorebook-entry-options">
                        <label><input type="checkbox" checked={entry.constant} onChange={(event) => updateEntry(index, 'constant', event.target.checked)}/><span>常驻注入</span></label>
                        <label><input type="checkbox" checked={entry.selective} onChange={(event) => updateEntry(index, 'selective', event.target.checked)}/><span>启用次关键词</span></label>
                        <label><input type="checkbox" checked={entry.use_regex} onChange={(event) => updateEntry(index, 'use_regex', event.target.checked)}/><span>正则匹配</span></label>
                      </div>
                      {entry.selective ? <label className="lorebook-entry-grid__wide"><span>次关键词</span><input className="input" value={entry.secondary_keys.join(', ')} onChange={(event) => updateEntry(index, 'secondary_keys', event.target.value.split(/[,，]/).map((item) => item.trimStart()))} placeholder="密室, 禁书区"/></label> : null}
                    </div>
                  </article>
                ))}
              </div>

            </div>
          ) : null}
        </div>

        <footer className="character-manager__footer">
          {activeTab === 'lorebook' ? (
            <div className="manager-actions">
              <button type="button" className="btn btn-secondary" disabled={savingLorebook} onClick={onClose}>关闭</button>
              <button type="button" className="btn btn-primary" disabled={savingLorebook || loadingLorebook} onClick={() => void saveLorebook()}><Save size={15}/>{savingLorebook ? '保存中…' : '保存世界书'}</button>
            </div>
          ) : (
            <div className="manager-actions">
              <button type="button" className="btn btn-secondary" disabled={saving} onClick={onClose}>取消</button>
              <button type="button" className="btn btn-primary" disabled={saving || !dirtyName} onClick={() => void saveBasic()}><Save size={15}/>{saving ? '保存中…' : mode === 'create' ? '创建角色' : '保存角色'}</button>
            </div>
          )}
        </footer>
      </section>
    </div>
  )
}
