import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BookMarked,
  Copy,
  Edit2,
  Eye,
  Feather,
  MapPin,
  MoreHorizontal,
  PanelRightOpen,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  Trash2,
  X,
} from 'lucide-react'
import { useAppStore } from '@/stores/appStore'
import { getModelConfigurationIssue } from '@/lib/modelConfig'
import type { Message } from '@/types'
import PromptPreviewModal from './PromptPreviewModal'
import ChoiceBar from './runtime/ChoiceBar'
import RuntimeMessageMeta from './runtime/RuntimeMessageMeta'
import StructuredMessage from './messages/StructuredMessage'
import { useToast } from './ui/ToastProvider'

export default function ChatView() {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const selectedCharacter = useAppStore((state) => state.selectedCharacter)
  const currentSession = useAppStore((state) => state.currentSession)
  const messages = useAppStore((state) => state.messages)
  const loadingMessages = useAppStore((state) => state.loadingMessages)
  const runtimeLoading = useAppStore((state) => state.runtimeLoading)
  const messageLoadError = useAppStore((state) => state.messageLoadError)
  const drafts = useAppStore((state) => state.drafts)
  const scrollPositions = useAppStore((state) => state.scrollPositions)
  const runtime = useAppStore((state) => state.runtime)
  const timeline = useAppStore((state) => state.timeline)
  const activeLorebook = useAppStore((state) => state.activeLorebook)
  const immersiveError = useAppStore((state) => state.immersiveError)
  const generatingMessageId = useAppStore((state) => state.generatingMessageId)
  const sendMessage = useAppStore((state) => state.sendMessage)
  const sendChoice = useAppStore((state) => state.sendChoice)
  const stopGeneration = useAppStore((state) => state.stopGeneration)
  const regenerateLast = useAppStore((state) => state.regenerateLast)
  const editMessage = useAppStore((state) => state.editMessage)
  const deleteMessage = useAppStore((state) => state.deleteMessage)
  const rollbackToMessage = useAppStore((state) => state.rollbackToMessage)
  const toggleRuntimeDrawer = useAppStore((state) => state.toggleRuntimeDrawer)
  const clearImmersiveError = useAppStore((state) => state.clearImmersiveError)
  const refreshCurrentSession = useAppStore((state) => state.refreshCurrentSession)
  const setDraft = useAppStore((state) => state.setDraft)
  const setScrollPosition = useAppStore((state) => state.setScrollPosition)
  const fetchSettings = useAppStore((state) => state.fetchSettings)
  const settings = useAppStore((state) => state.settings)

  const [inputValue, setInputValue] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editContent, setEditContent] = useState('')
  const [showPromptPreview, setShowPromptPreview] = useState(false)
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)
  const [pendingSubmittedText, setPendingSubmittedText] = useState<string | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messageListRef = useRef<HTMLElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const autoScrollRef = useRef(true)
  const activeSessionRef = useRef<string | null>(null)
  const restoredSessionRef = useRef<string | null>(null)
  const skipNextAutoScrollRef = useRef(false)

  useEffect(() => {
    if (!currentSession) return
    setInputValue(drafts[currentSession.id] || '')
  }, [currentSession?.id])

  useEffect(() => {
    if (!currentSession || !pendingSubmittedText) return
    const confirmed = messages.some((message) =>
      message.role === 'user'
      && !message.id.startsWith('local-')
      && message.content === pendingSubmittedText
    )
    if (!confirmed) return
    if (inputValue === pendingSubmittedText) setInputValue('')
    setDraft(currentSession.id, '')
    setPendingSubmittedText(null)
  }, [currentSession?.id, inputValue, messages, pendingSubmittedText, setDraft])

  useLayoutEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 192)}px`
  }, [inputValue])

  useLayoutEffect(() => {
    const sessionId = currentSession?.id || null
    if (activeSessionRef.current !== sessionId) {
      activeSessionRef.current = sessionId
      restoredSessionRef.current = null
      autoScrollRef.current = true
    }
    if (!sessionId || loadingMessages || runtimeLoading || restoredSessionRef.current === sessionId) return

    const messageList = messageListRef.current
    if (!messageList) return
    const hasSavedPosition = Object.prototype.hasOwnProperty.call(scrollPositions, sessionId)
    messageList.scrollTop = hasSavedPosition ? scrollPositions[sessionId] : messageList.scrollHeight
    autoScrollRef.current = messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < 120
    restoredSessionRef.current = sessionId
    skipNextAutoScrollRef.current = true
  }, [currentSession?.id, loadingMessages, messages.length, runtime?.revision, runtimeLoading, scrollPositions])

  useEffect(() => {
    const sessionId = currentSession?.id
    if (!sessionId || loadingMessages || runtimeLoading || restoredSessionRef.current !== sessionId) return
    if (skipNextAutoScrollRef.current) {
      skipNextAutoScrollRef.current = false
      return
    }
    if (autoScrollRef.current) messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [currentSession?.id, loadingMessages, messages, runtime?.revision, runtimeLoading])

  const handleScroll = (event: React.UIEvent<HTMLElement>) => {
    const target = event.currentTarget
    autoScrollRef.current = target.scrollHeight - target.scrollTop - target.clientHeight < 120
    if (currentSession) setScrollPosition(currentSession.id, target.scrollTop)
  }

  const ensureModelConfiguration = async () => {
    if (!useAppStore.getState().settings) {
      try {
        await fetchSettings()
      } catch {
        showToast('模型设置加载失败，请打开设置确认后重试。', 'error', {
          label: '打开设置',
          onClick: () => navigate('/settings'),
        })
        return false
      }
    }

    const issue = getModelConfigurationIssue(useAppStore.getState().settings)
    if (!issue) return true

    showToast(issue.message, 'error', {
      label: '打开设置',
      onClick: () => navigate('/settings'),
    })
    return false
  }

  const submitText = async (content: string) => {
    const value = content.trim()
    if (!value || generatingMessageId) return
    if (!(await ensureModelConfiguration())) return

    setPendingSubmittedText(value)
    void sendMessage(value)
    autoScrollRef.current = true
    requestAnimationFrame(() => textareaRef.current?.focus())
  }

  const submitChoice = async (choice: string) => {
    if (generatingMessageId || !(await ensureModelConfiguration())) return
    await sendChoice(choice)
  }

  const regenerateWithConfigurationCheck = async () => {
    if (generatingMessageId || !(await ensureModelConfiguration())) return
    await regenerateLast()
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.nativeEvent.isComposing) return
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submitText(inputValue)
    }
  }

  const startEdit = (message: Message) => {
    setEditingId(message.id)
    setEditContent(message.content)
    setMenuOpenId(null)
  }

  const saveEdit = async () => {
    if (!editingId || !editContent.trim()) return
    await editMessage(editingId, editContent.trim())
    setEditingId(null)
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm('确定要删除这条消息吗？涉及状态的历史回复建议使用“回到此处”。')) return
    try {
      await deleteMessage(id)
    } finally {
      setMenuOpenId(null)
    }
  }

  if (!selectedCharacter) {
    return (
      <div className="flex-1 flex items-center justify-center tavern-bg">
        <div className="text-center animate-fade-in">
          <div className="w-20 h-20 mx-auto mb-5 rounded-2xl bg-gradient-to-br from-tavern-gold-600/10 to-tavern-mist-700/10 border border-tavern-border-gold/20 flex items-center justify-center">
            <Feather size={32} className="text-tavern-gold-400/60" />
          </div>
          <p className="text-tavern-text-secondary mb-1.5">选择一张角色卡，进入它的世界</p>
          <p className="text-sm text-tavern-text-muted">状态、关系与事件会随剧情持续演进</p>
        </div>
      </div>
    )
  }

  if (!currentSession) {
    return (
      <div className="flex-1 flex items-center justify-center tavern-bg">
        <div className="text-center animate-fade-in">
          <div className="w-20 h-20 mx-auto mb-5 rounded-2xl bg-gradient-to-br from-tavern-gold-600/10 to-tavern-mist-700/10 border border-tavern-border-gold/20 flex items-center justify-center">
            <Sparkles size={32} className="text-tavern-gold-400/60" />
          </div>
          <p className="text-tavern-text-secondary mb-1.5">开启一条新的剧情线</p>
          <p className="text-sm text-tavern-text-muted">点击左侧“新建会话”建立独立世界状态</p>
        </div>
      </div>
    )
  }

  const lastAssistant = [...messages].reverse().find((message) => message.role === 'assistant')
  const lastTurn = runtime?.last_turn
  const choices = lastTurn && lastAssistant?.id === lastTurn.message_id ? lastTurn.choices : []
  const modeLabel = runtime?.profile.mode === 'adventure' ? '冒险' : '关系'
  const scene = runtime?.state.scene
  const expression = runtime?.state.character?.expression || runtime?.state.character?.mood
  const estimatedTokens = Math.max(0, Math.ceil(inputValue.length / 3))

  return (
    <div className={`flex-1 min-w-0 flex flex-col h-screen overflow-hidden tavern-bg paper-texture immersive-stage immersive-stage--${runtime?.profile.mode || 'relationship'}`}>
      <header className="glass-bar px-4 sm:px-5 py-3 flex items-center justify-between flex-shrink-0 z-10">
        <div className="flex items-center gap-3 min-w-0">
          <div className="relative w-10 h-10 rounded-xl overflow-hidden ring-1 ring-tavern-border-gold/20 flex-shrink-0">
            {selectedCharacter.avatar_path ? (
              <img src={selectedCharacter.avatar_path} alt="" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full bg-tavern-bg-tertiary flex items-center justify-center font-medium text-tavern-text-secondary">{selectedCharacter.name.charAt(0)}</div>
            )}
            <i className={`absolute bottom-1 right-1 w-2 h-2 rounded-full ${generatingMessageId ? 'bg-tavern-gold-400 animate-pulse' : 'bg-emerald-400'}`} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-tavern-text-primary truncate">{selectedCharacter.name}</h2>
              {expression ? <span className="tag tag-gold hidden sm:inline">{expression}</span> : null}
            </div>
            <p className="text-[11px] text-tavern-text-muted truncate flex items-center gap-1 max-w-[48vw] lg:max-w-[360px]">
              <MapPin size={10}/>{scene?.location || selectedCharacter.scenario || currentSession.title}
              {scene?.time ? <span>· {scene.time}</span> : null}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="hidden md:inline text-[10px] text-tavern-text-muted px-2 py-1 rounded-md bg-tavern-bg-tertiary/40 border border-tavern-border-subtle">{settings?.model || '默认模型'}</span>
          <button onClick={() => setShowPromptPreview(true)} className="btn btn-secondary btn-sm" title="Prompt 预览"><Eye size={14}/><span className="hidden sm:inline">Prompt</span></button>
          {lastAssistant && !generatingMessageId ? <button onClick={() => void regenerateWithConfigurationCheck()} className="btn btn-secondary btn-sm" title="重新生成并恢复旧状态"><RotateCcw size={14}/><span className="hidden sm:inline">重生成</span></button> : null}
          <button onClick={() => toggleRuntimeDrawer(true)} className="btn btn-secondary btn-sm lg:hidden" title="打开沉浸状态面板"><PanelRightOpen size={15}/></button>
        </div>
      </header>

      {immersiveError ? (
        <div className="immersive-error-banner"><span>{immersiveError}</span><button onClick={clearImmersiveError}><X size={14}/></button></div>
      ) : null}

      <div className="immersive-scene-ribbon">
        <span><CompassMark />{scene?.objective || (runtime?.profile.mode === 'adventure' ? '踏上冒险' : '延续故事')}</span>
        <span>{scene?.weather || scene?.atmosphere || '世界正在等待你的行动'}</span>
      </div>

      <main data-testid="message-list" ref={messageListRef} className="flex-1 overflow-y-auto px-3 sm:px-4 py-5 sm:py-6 scrollbar-thin" onScroll={handleScroll}>
        <div className="max-w-4xl mx-auto space-y-5">
          {loadingMessages && messages.length === 0 ? <div className="session-loading-card"><span className="generating-dots"><span/><span/><span/></span><p>正在恢复会话…</p></div> : null}
          {messageLoadError && messages.length === 0 ? <div className="session-load-error"><p>{messageLoadError}</p><button className="btn btn-secondary btn-sm" onClick={() => void refreshCurrentSession()}>重试</button></div> : null}
          {runtime?.profile.mode === 'adventure' && messages.length <= 1 ? (
            <button className="adventure-launch-card" onClick={() => toggleRuntimeDrawer(true)}>
              <span><SwordsGlyph /></span>
              <div><strong>建立你的冒险者</strong><p>打开右侧状态面板，使用原生创建器保存角色属性后开始旅程。</p></div>
              <PanelRightOpen size={18}/>
            </button>
          ) : null}

          {messages.map((message, index) => {
            const turn = timeline.find((item) => item.message_id === message.id)
            const isAssistant = message.role === 'assistant'
            return (
              <article key={message.id} className={`flex gap-3 ${message.id.startsWith('local-') || message.generation_status === 'generating' ? 'animate-slide-up' : ''} ${message.role === 'user' ? 'flex-row-reverse' : ''}`}>
                {isAssistant ? (
                  <div className="w-9 h-9 rounded-lg overflow-hidden flex-shrink-0 ring-1 ring-tavern-border-gold/20 mt-0.5">
                    {selectedCharacter.avatar_path ? <img src={selectedCharacter.avatar_path} alt="" className="w-full h-full object-cover"/> : <div className="w-full h-full bg-tavern-bg-tertiary flex items-center justify-center text-sm font-medium text-tavern-text-secondary">{selectedCharacter.name.charAt(0)}</div>}
                  </div>
                ) : null}

                <div className={`relative group ${isAssistant ? 'max-w-[88%] min-w-0' : 'max-w-[78%]'}`}>
                  {isAssistant ? <div className="text-[11px] text-tavern-gold-400/80 font-medium mb-1 px-1 flex items-center gap-2"><span>{selectedCharacter.name}</span>{turn?.expression ? <span className="text-tavern-text-muted">· {turn.expression}</span> : null}</div> : null}

                  {editingId === message.id ? (
                    <div className="card-parchment min-w-[280px]">
                      <textarea value={editContent} onChange={(event) => setEditContent(event.target.value)} className="textarea w-full h-32 mb-2 bg-tavern-bg-primary/50" autoFocus/>
                      <div className="flex justify-end gap-2"><button onClick={() => setEditingId(null)} className="btn btn-secondary btn-sm">取消</button><button onClick={() => void saveEdit()} className="btn btn-primary btn-sm">保存</button></div>
                    </div>
                  ) : (
                    <>
                      <div className={message.role === 'user' ? 'msg-user' : 'msg-assistant'}>
                        <StructuredMessage message={message} state={turn?.state_after || runtime?.state}/>
                        {message.generation_status === 'generating' ? <span className="generating-dots ml-1 align-middle"><span/><span/><span/></span> : null}
                        {message.generation_status === 'stopped' ? <p className="text-xs text-tavern-text-muted mt-2 italic">（已停止，本轮状态未应用）</p> : null}
                        {message.generation_status === 'error' ? <p className="text-xs text-tavern-rose-400 mt-2 italic">（生成出错，本轮状态未应用）</p> : null}
                      </div>

                      {isAssistant ? <RuntimeMessageMeta turn={turn} canRollback={Boolean(turn && turn.message_id !== lastTurn?.message_id)} onRollback={turn ? () => void rollbackToMessage(turn.message_id) : undefined}/> : null}

                      <div className={`message-actions ${message.role === 'user' ? 'message-actions--user' : ''}`}>
                        <button onClick={() => void navigator.clipboard.writeText(message.content)} title="复制"><Copy size={12}/></button>
                        <button onClick={() => startEdit(message)} title="编辑"><Edit2 size={12}/></button>
                        <div className="relative">
                          <button onClick={() => setMenuOpenId(menuOpenId === message.id ? null : message.id)} title="更多"><MoreHorizontal size={13}/></button>
                          {menuOpenId === message.id ? <div className="message-menu"><button onClick={() => void handleDelete(message.id)}><Trash2 size={12}/>删除消息</button></div> : null}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </article>
            )
          })}
          <div ref={messagesEndRef}/>
        </div>
      </main>

      <footer className="immersive-composer-shell">
        <div className="max-w-4xl mx-auto">
          <ChoiceBar choices={choices} disabled={Boolean(generatingMessageId)} onChoose={(choice) => void submitChoice(choice)}/>
          <div className="immersive-composer">
            <textarea
              data-testid="chat-composer"
              ref={textareaRef}
              value={inputValue}
              onChange={(event) => {
                setInputValue(event.target.value)
                if (currentSession) setDraft(currentSession.id, event.target.value)
              }}
              onKeyDown={handleKeyDown}
              placeholder={runtime?.profile.mode === 'adventure' ? '描述行动、对话，或直接点击上方行动选项…' : `对 ${selectedCharacter.name} 说些什么，或描述你的行动…`}
              className="textarea immersive-composer__input"
              rows={1}
            />
            {generatingMessageId ? (
              <button onClick={() => void stopGeneration()} className="immersive-send immersive-send--stop" title="停止生成"><Square size={17} fill="currentColor"/></button>
            ) : (
              <button onClick={() => void submitText(inputValue)} className="immersive-send" disabled={!inputValue.trim()} title="发送"><Send size={18}/></button>
            )}
          </div>
          <div className="immersive-composer-meta">
            <span>{modeLabel}模式 · 状态 r{runtime?.revision ?? 0}</span>
            <span><BookMarked size={10}/>{activeLorebook.length} 条设定生效</span>
            <span>约 {estimatedTokens} tokens</span>
            <span className="hidden sm:inline">Enter 发送 · Shift+Enter 换行</span>
          </div>
        </div>
      </footer>

      {showPromptPreview ? <PromptPreviewModal sessionId={currentSession.id} message={inputValue || '（预览下一轮）'} onClose={() => setShowPromptPreview(false)}/> : null}
    </div>
  )
}

function CompassMark() {
  return <Sparkles size={12}/>
}

function SwordsGlyph() {
  return <Sparkles size={22}/>
}
