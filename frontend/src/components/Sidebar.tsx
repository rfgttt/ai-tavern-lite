import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Brain,
  Download,
  Feather,
  GitBranch,
  Menu,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings,
  Trash2,
  Upload,
  UserPlus,
  UserRound,
  Users,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react'
import { exportCharacter as exportCharacterApi, exportSession as exportSessionApi } from '@/api'
import { useAppStore } from '@/stores/appStore'
import type { Character, CharacterGroup, SessionCreateOptions } from '@/types'
import { getErrorMessage } from '@/lib/errors'
import { getModelConfigurationIssue } from '@/lib/modelConfig'
import PersonaManager from './PersonaManager'
import GroupManager from './GroupManager'
import BranchManager from './BranchManager'
import CharacterManager from './CharacterManager'
import NewSessionWizard from './NewSessionWizard'
import ConfirmDialog from './ui/ConfirmDialog'
import { useToast } from './ui/ToastProvider'

type CharacterEditorState = {
  mode: 'create' | 'edit'
  character: Character | null
} | null

const downloadJson = (data: unknown, filename: string) => {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

const safeFilename = (value: string, fallback: string) => value.replace(/[\\/:*?"<>|]/g, '_').trim() || fallback

export default function Sidebar() {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const {
    characters,
    selectedCharacter,
    sessions,
    currentSession,
    sidebarOpen,
    toggleSidebar,
    fetchCharacters,
    selectCharacter,
    createSession,
    selectSession,
    renameSession,
    deleteSession,
    deleteCharacter,
    fetchSettings,
    settings,
  } = useAppStore()

  const [searchQuery, setSearchQuery] = useState('')
  const [personaOpen, setPersonaOpen] = useState(false)
  const [groupOpen, setGroupOpen] = useState(false)
  const [branchOpen, setBranchOpen] = useState(false)
  const [sessionMenuId, setSessionMenuId] = useState<string | null>(null)
  const [characterMenuId, setCharacterMenuId] = useState<string | null>(null)
  const [characterEditor, setCharacterEditor] = useState<CharacterEditorState>(null)
  const [pendingDeleteCharacter, setPendingDeleteCharacter] = useState<Character | null>(null)
  const [deletingCharacter, setDeletingCharacter] = useState(false)
  const [newSessionWizard, setNewSessionWizard] = useState<{ groupId?: string } | null>(null)

  useEffect(() => {
    void fetchCharacters().catch((error) => showToast(getErrorMessage(error, '角色列表加载失败'), 'error'))
  }, [fetchCharacters, showToast])

  const filteredCharacters = characters.filter((character) =>
    character.name.toLowerCase().includes(searchQuery.toLowerCase()),
  )

  const handleImportClick = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json,.png'
    input.onchange = async (event) => {
      const file = (event.target as HTMLInputElement).files?.[0]
      if (!file) return
      try {
        const character = await useAppStore.getState().importCharacter(file)
        selectCharacter(character)
        showToast(`已导入角色“${character.name}”`, 'success')
      } catch (error) {
        showToast(getErrorMessage(error, '角色导入失败'), 'error')
      }
    }
    input.click()
  }

  const closeMobileSidebar = () => {
    if (window.matchMedia('(max-width: 1023px)').matches && useAppStore.getState().sidebarOpen) {
      toggleSidebar()
    }
  }

  const openModelSettings = () => navigate('/settings')

  const ensureModelConfiguration = async () => {
    if (!useAppStore.getState().settings) {
      try {
        await fetchSettings()
      } catch (error) {
        showToast(getErrorMessage(error, '模型设置加载失败'), 'error', {
          label: '打开设置',
          onClick: openModelSettings,
        })
        return false
      }
    }

    const issue = getModelConfigurationIssue(useAppStore.getState().settings)
    if (!issue) return true

    showToast(issue.message, 'error', {
      label: '打开设置',
      onClick: openModelSettings,
    })
    return false
  }

  const handleNewChat = () => {
    if (!characters.length) {
      showToast('请先创建或导入至少一个角色', 'info')
      return
    }
    setNewSessionWizard({})
  }

  const handleStartGroup = (group: CharacterGroup) => {
    setNewSessionWizard({ groupId: group.id })
  }

  const handleCreateSession = async (characterId: string, options: SessionCreateOptions) => {
    if (!(await ensureModelConfiguration())) {
      throw new Error('请先完成模型配置')
    }

    const character = characters.find((item) => item.id === characterId)
    if (!character) throw new Error('所选角色不存在')

    selectCharacter(character)
    const session = await createSession(characterId, options)
    await selectSession(session)
    setNewSessionWizard(null)
    navigate('/chat')
    closeMobileSidebar()
    showToast(`已创建会话“${session.title}”`, 'success')
  }

  const handleExportSession = async (session: typeof sessions[number]) => {
    try {
      const response = await exportSessionApi(session.id)
      downloadJson(response.data, `${safeFilename(session.title, 'AI-Tavern-Session')}.json`)
      showToast('会话已导出', 'success')
    } catch (error) {
      showToast(getErrorMessage(error, '会话导出失败'), 'error')
    } finally {
      setSessionMenuId(null)
    }
  }

  const handleExportCharacter = async (character: Character) => {
    try {
      const response = await exportCharacterApi(character.id)
      downloadJson(response.data, `${safeFilename(character.name, 'AI-Tavern-Character')}.json`)
      showToast(`角色“${character.name}”已导出`, 'success')
    } catch (error) {
      showToast(getErrorMessage(error, '角色导出失败'), 'error')
    } finally {
      setCharacterMenuId(null)
    }
  }

  const confirmDeleteCharacter = async () => {
    if (!pendingDeleteCharacter) return
    setDeletingCharacter(true)
    try {
      await deleteCharacter(pendingDeleteCharacter.id)
      showToast(`角色“${pendingDeleteCharacter.name}”已删除`, 'success')
      setPendingDeleteCharacter(null)
    } catch (error) {
      showToast(getErrorMessage(error, '角色删除失败'), 'error')
    } finally {
      setDeletingCharacter(false)
    }
  }

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const days = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))
    if (days === 0) return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    if (days < 7) return `${days}天前`
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  const isConnected = settings?.mock_llm || settings?.api_key_configured

  return (
    <>
      <button
        type="button"
        onClick={toggleSidebar}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-tavern-glass-medium backdrop-blur-md rounded-lg border border-tavern-border-subtle text-tavern-text-secondary"
        aria-label={sidebarOpen ? '关闭侧栏' : '打开侧栏'}
      >
        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      <div
        className={`fixed lg:static inset-y-0 left-0 z-40 w-[260px] bg-tavern-bg-secondary/95 border-r border-tavern-border-subtle transform transition-transform duration-300 ease-tavern backdrop-blur-md flex flex-col ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0 lg:w-0 lg:overflow-hidden lg:border-r-0'
        }`}
      >
        <div className="flex flex-col h-full">
          <div className="px-4 pt-5 pb-4 border-b border-tavern-border-subtle">
            <Link to="/" className="flex items-center gap-2.5 group">
              <div className="relative w-9 h-9 rounded-lg bg-gradient-to-br from-tavern-gold-600/20 to-tavern-mist-700/20 flex items-center justify-center border border-tavern-border-gold/30 group-hover:border-tavern-border-gold/50 transition-all">
                <Feather size={18} className="text-tavern-gold-400" />
                <Moon size={10} className="absolute -top-0.5 -right-0.5 text-tavern-mist-400" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-semibold text-tavern-text-primary tracking-wide">AI Tavern</span>
                <span className="text-[10px] text-tavern-text-muted tracking-widest uppercase">Lite Edition</span>
              </div>
            </Link>
            <div className="flex items-center gap-1.5 mt-3 px-1">
              {isConnected ? (
                <><Wifi size={12} className="text-emerald-400" /><span className="text-[11px] text-emerald-400/80">{settings?.mock_llm ? 'Mock 模式' : '已连接'}</span></>
              ) : (
                <><WifiOff size={12} className="tavern-text-muted" /><span className="text-[11px] text-tavern-text-muted">未配置</span></>
              )}
            </div>
          </div>

          <div className="px-3 py-3 border-b border-tavern-border-subtle">
            <div className="flex items-center justify-between mb-2.5 px-1">
              <span className="section-label mb-0">角色名册</span>
              <div className="flex items-center gap-0.5">
                <button type="button" onClick={handleImportClick} className="btn-icon p-1" title="导入角色卡"><Upload size={14} /></button>
                <button type="button" onClick={() => setCharacterEditor({ mode: 'create', character: null })} className="btn-icon p-1" title="新建角色"><UserPlus size={14} /></button>
              </div>
            </div>

            <div className="relative mb-2.5">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-tavern-text-muted" />
              <input type="text" placeholder="搜索角色..." value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} className="input input-search py-1.5 text-xs bg-tavern-bg-tertiary/40" />
            </div>

            <div className="max-h-52 overflow-y-auto space-y-0.5 scrollbar-thin pr-0.5">
              {filteredCharacters.length === 0 ? <p className="text-xs text-tavern-text-muted text-center py-4">暂无角色</p> : null}
              {filteredCharacters.map((character) => {
                const isSelected = selectedCharacter?.id === character.id
                return (
                  <div key={character.id} className="relative group/character">
                    <button
                      type="button"
                      aria-label={`选择角色 ${character.name}`}
                      onClick={() => { selectCharacter(character); setCharacterMenuId(null) }}
                      className={`relative w-full flex items-center gap-2.5 pl-2 pr-8 py-2 rounded-lg text-left transition-all duration-200 group ${
                        isSelected
                          ? 'bg-tavern-bg-tertiary/70 border border-tavern-border-gold/40 shadow-glow-gold'
                          : 'hover:bg-tavern-bg-tertiary/40 border border-transparent'
                      }`}
                    >
                      {isSelected ? <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-gradient-to-b from-tavern-gold-400 to-tavern-gold-600 rounded-r shadow-[0_0_6px_rgba(230,169,74,0.5)]" /> : null}
                      <div className={`relative w-8 h-8 rounded-full overflow-hidden flex-shrink-0 ${isSelected ? 'ring-1 ring-tavern-gold-500/40 ring-offset-1 ring-offset-tavern-bg-secondary' : ''}`}>
                        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-tavern-gold-500/10 to-transparent pointer-events-none" />
                        {character.avatar_path ? <img src={character.avatar_path} alt="" className="w-full h-full object-cover" /> : <div className="w-full h-full bg-tavern-bg-tertiary flex items-center justify-center text-xs font-medium text-tavern-text-secondary">{character.name.charAt(0)}</div>}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm truncate ${isSelected ? 'text-tavern-gold-300' : 'text-tavern-text-primary'}`}>{character.name}</div>
                        <div className="text-[10px] text-tavern-text-muted truncate">{character.description ? character.description.slice(0, 20) : '未设定描述'}</div>
                      </div>
                    </button>
                    <button
                      type="button"
                      aria-label={`角色菜单 ${character.name}`}
                      className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded opacity-60 hover:opacity-100 hover:bg-tavern-bg-tertiary"
                      onClick={(event) => { event.stopPropagation(); setCharacterMenuId(characterMenuId === character.id ? null : character.id) }}
                    ><MoreHorizontal size={13}/></button>
                    {characterMenuId === character.id ? (
                      <div className="absolute right-1 top-10 z-50 min-w-32 rounded-lg border border-tavern-border-subtle bg-tavern-bg-secondary shadow-xl p-1">
                        <button type="button" className="sidebar-item w-full text-xs" onClick={() => { setCharacterEditor({ mode: 'edit', character }); setCharacterMenuId(null) }}><Pencil size={13}/><span>编辑角色</span></button>
                        <button type="button" className="sidebar-item w-full text-xs" onClick={() => void handleExportCharacter(character)}><Download size={13}/><span>导出角色</span></button>
                        <button type="button" className="sidebar-item w-full text-xs text-red-300" onClick={() => { setPendingDeleteCharacter(character); setCharacterMenuId(null) }}><Trash2 size={13}/><span>删除角色</span></button>
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          </div>

          <div className="flex-1 px-3 py-3 overflow-hidden flex flex-col">
            <div className="flex items-center justify-between mb-2.5 px-1">
              <span className="section-label mb-0">会话记录</span>
              <button type="button" onClick={handleNewChat} className="btn-icon p-1" title="新建对话"><Plus size={14} /></button>
            </div>
            <div className="flex-1 overflow-y-auto space-y-0.5 scrollbar-thin pr-0.5">
              {!selectedCharacter ? <p className="text-xs text-tavern-text-muted text-center py-4">请先选择角色</p> : null}
              {selectedCharacter && sessions.length === 0 ? <p className="text-xs text-tavern-text-muted text-center py-4">暂无会话</p> : null}
              {sessions.map((session) => {
                const isActive = currentSession?.id === session.id
                return (
                  <div key={session.id} className="relative group/session">
                    <button type="button" onClick={() => { void selectSession(session); navigate('/chat'); closeMobileSidebar() }} className={`w-full flex items-center justify-between gap-2 pl-2.5 pr-8 py-1.5 rounded-lg text-left text-xs transition-all duration-200 ${isActive ? 'bg-tavern-bg-tertiary/50 text-tavern-gold-300' : 'text-tavern-text-secondary hover:bg-tavern-bg-tertiary/30 hover:text-tavern-text-primary'}`}>
                      <span className="truncate flex-1">{session.title}</span><span className="text-[10px] text-tavern-text-muted flex-shrink-0">{formatTime(session.updated_at)}</span>
                    </button>
                    <button type="button" aria-label="会话菜单" className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded opacity-60 hover:opacity-100 hover:bg-tavern-bg-tertiary" onClick={(event) => { event.stopPropagation(); setSessionMenuId(sessionMenuId === session.id ? null : session.id) }}><MoreHorizontal size={13}/></button>
                    {sessionMenuId === session.id ? <div className="absolute right-1 top-8 z-50 min-w-28 rounded-lg border border-tavern-border-subtle bg-tavern-bg-secondary shadow-xl p-1">
                      <button type="button" className="sidebar-item w-full text-xs" onClick={() => { const title = window.prompt('重命名会话', session.title); if (title?.trim()) void renameSession(session.id, title); setSessionMenuId(null) }}><Pencil size={13}/><span>重命名</span></button>
                      <button type="button" className="sidebar-item w-full text-xs" onClick={() => void handleExportSession(session)}><Download size={13}/><span>导出会话</span></button>
                      <button type="button" className="sidebar-item w-full text-xs text-red-300" onClick={() => { if (window.confirm(`确定删除会话“${session.title}”吗？\n\n该会话中的消息、剧情分支、运行时状态和会话记忆都会删除，无法撤销。`)) void deleteSession(session.id); setSessionMenuId(null) }}><Trash2 size={13}/><span>删除会话</span></button>
                    </div> : null}
                  </div>
                )
              })}
            </div>
          </div>

          <div className="px-3 py-3 border-t border-tavern-border-subtle space-y-0.5">
            <button type="button" onClick={() => setPersonaOpen(true)} className="sidebar-item w-full"><UserRound size={16}/><span>Persona</span></button>
            <button type="button" onClick={() => setGroupOpen(true)} className="sidebar-item w-full"><Users size={16}/><span>多角色编组</span></button>
            <button type="button" onClick={() => setBranchOpen(true)} className="sidebar-item w-full"><GitBranch size={16}/><span>剧情分支</span></button>
            <Link to="/memory" className="sidebar-item"><Brain size={16}/><span>长期记忆</span></Link>
            <Link data-testid="open-settings" to="/settings" className="sidebar-item"><Settings size={16}/><span>设置</span></Link>
          </div>
        </div>
      </div>

      {sidebarOpen ? <div className="lg:hidden fixed inset-0 bg-black/60 z-30 backdrop-blur-sm animate-fade-in" onClick={toggleSidebar} /> : null}
      <PersonaManager open={personaOpen} onClose={() => setPersonaOpen(false)}/>
      <GroupManager open={groupOpen} onClose={() => setGroupOpen(false)} onStartGroup={handleStartGroup}/>
      <BranchManager open={branchOpen} onClose={() => setBranchOpen(false)}/>
      <NewSessionWizard
        open={Boolean(newSessionWizard)}
        characters={characters}
        initialCharacterId={selectedCharacter?.id}
        initialGroupId={newSessionWizard?.groupId}
        onClose={() => setNewSessionWizard(null)}
        onCreate={handleCreateSession}
      />
      <CharacterManager
        open={Boolean(characterEditor)}
        mode={characterEditor?.mode || 'create'}
        character={characterEditor?.character || null}
        onClose={() => setCharacterEditor(null)}
        onSaved={(character) => {
          if (characterEditor?.mode === 'create') selectCharacter(character)
        }}
      />
      <ConfirmDialog
        open={Boolean(pendingDeleteCharacter)}
        title="删除角色"
        description={`确定删除角色“${pendingDeleteCharacter?.name || ''}”吗？相关会话、消息和角色记忆也会被永久删除。`}
        confirmLabel="删除角色"
        destructive
        busy={deletingCharacter}
        onCancel={() => setPendingDeleteCharacter(null)}
        onConfirm={() => void confirmDeleteCharacter()}
      />
    </>
  )
}
