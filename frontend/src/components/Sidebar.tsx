import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  MessageSquare,
  Settings,
  Plus,
  Upload,
  Search,
  Menu,
  X,
  Brain,
  Moon,
  Feather,
  Wifi,
  WifiOff,
  UserPlus,
  Users,
  UserRound,
  GitBranch,
  MoreHorizontal,
  Pencil,
  Download,
  Trash2,
} from 'lucide-react'
import { useAppStore } from '@/stores/appStore'
import { exportSession as exportSessionApi } from '@/api'
import PersonaManager from './PersonaManager'
import GroupManager from './GroupManager'
import BranchManager from './BranchManager'

export default function Sidebar() {
  const navigate = useNavigate()
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
    settings,
  } = useAppStore()

  const [searchQuery, setSearchQuery] = useState('')
  const [personaOpen, setPersonaOpen] = useState(false)
  const [groupOpen, setGroupOpen] = useState(false)
  const [branchOpen, setBranchOpen] = useState(false)
  const [sessionMenuId, setSessionMenuId] = useState<string | null>(null)

  useEffect(() => {
    fetchCharacters()
  }, [])

  const filteredCharacters = characters.filter((c) =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleImportClick = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json,.png'
    input.onchange = async (e: any) => {
      const file = e.target.files?.[0]
      if (file) {
        try {
          const char = await useAppStore.getState().importCharacter(file)
          selectCharacter(char)
        } catch (err) {
          alert('导入失败: ' + (err as any)?.response?.data?.detail || err)
        }
      }
    }
    input.click()
  }

  const closeMobileSidebar = () => {
    if (window.matchMedia('(max-width: 1023px)').matches && useAppStore.getState().sidebarOpen) {
      toggleSidebar()
    }
  }

  const handleNewChat = async () => {
    if (!selectedCharacter) {
      alert('请先选择一个角色')
      return
    }
    try {
      const session = await createSession(selectedCharacter.id)
      await selectSession(session)
      navigate('/chat')
      closeMobileSidebar()
    } catch (err) {
      console.error(err)
    }
  }

  const handleExportSession = async (session: typeof sessions[number]) => {
    const response = await exportSessionApi(session.id)
    const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${session.title.replace(/[\\/:*?"<>|]/g, '_') || 'AI-Tavern-Session'}.json`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
    setSessionMenuId(null)
  }

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))

    if (days === 0) {
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    } else if (days < 7) {
      return `${days}天前`
    } else {
      return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
    }
  }

  const isConnected = settings?.mock_llm || settings?.api_key_configured

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={toggleSidebar}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-tavern-glass-medium backdrop-blur-md rounded-lg border border-tavern-border-subtle text-tavern-text-secondary"
      >
        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Sidebar */}
      <div
        className={`fixed lg:static inset-y-0 left-0 z-40 w-[260px] bg-tavern-bg-secondary/95 border-r border-tavern-border-subtle transform transition-transform duration-300 ease-tavern backdrop-blur-md flex flex-col ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0 lg:w-0 lg:overflow-hidden lg:border-r-0'
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Header - Tavern Brand */}
          <div className="px-4 pt-5 pb-4 border-b border-tavern-border-subtle">
            <Link to="/" className="flex items-center gap-2.5 group">
              <div className="relative w-9 h-9 rounded-lg bg-gradient-to-br from-tavern-gold-600/20 to-tavern-mist-700/20 flex items-center justify-center border border-tavern-border-gold/30 group-hover:border-tavern-border-gold/50 transition-all">
                <Feather size={18} className="text-tavern-gold-400" />
                <Moon size={10} className="absolute -top-0.5 -right-0.5 text-tavern-mist-400" />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-semibold text-tavern-text-primary tracking-wide">
                  AI Tavern
                </span>
                <span className="text-[10px] text-tavern-text-muted tracking-widest uppercase">
                  Lite Edition
                </span>
              </div>
            </Link>

            {/* Connection status */}
            <div className="flex items-center gap-1.5 mt-3 px-1">
              {isConnected ? (
                <>
                  <Wifi size={12} className="text-emerald-400" />
                  <span className="text-[11px] text-emerald-400/80">
                    {settings?.mock_llm ? 'Mock 模式' : '已连接'}
                  </span>
                </>
              ) : (
                <>
                  <WifiOff size={12} className="tavern-text-muted" />
                  <span className="text-[11px] text-tavern-text-muted">未配置</span>
                </>
              )}
            </div>
          </div>

          {/* Character section - 角色名册 */}
          <div className="px-3 py-3 border-b border-tavern-border-subtle">
            <div className="flex items-center justify-between mb-2.5 px-1">
              <span className="section-label mb-0">角色名册</span>
              <div className="flex items-center gap-0.5">
                <button
                  onClick={handleImportClick}
                  className="btn-icon p-1"
                  title="导入角色卡"
                >
                  <Upload size={14} />
                </button>
                <button
                  className="btn-icon p-1"
                  title="新建角色"
                >
                  <UserPlus size={14} />
                </button>
              </div>
            </div>

            {/* Search */}
            <div className="relative mb-2.5">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-tavern-text-muted" />
              <input
                type="text"
                placeholder="搜索角色..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="input input-search py-1.5 text-xs bg-tavern-bg-tertiary/40"
              />
            </div>

            {/* Character list */}
            <div className="max-h-52 overflow-y-auto space-y-0.5 scrollbar-thin pr-0.5">
              {filteredCharacters.length === 0 && (
                <p className="text-xs text-tavern-text-muted text-center py-4">
                  暂无角色
                </p>
              )}
              {filteredCharacters.map((char) => {
                const isSelected = selectedCharacter?.id === char.id
                return (
                  <button
                    key={char.id}
                    onClick={() => selectCharacter(char)}
                    className={`relative w-full flex items-center gap-2.5 px-2 py-2 rounded-lg text-left transition-all duration-200 group ${
                      isSelected
                        ? 'bg-tavern-bg-tertiary/70 border border-tavern-border-gold/40 shadow-glow-gold'
                        : 'hover:bg-tavern-bg-tertiary/40 border border-transparent'
                    }`}
                  >
                    {/* Active indicator bar */}
                    {isSelected && (
                      <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-gradient-to-b from-tavern-gold-400 to-tavern-gold-600 rounded-r shadow-[0_0_6px_rgba(230,169,74,0.5)]" />
                    )}

                    {/* Avatar with halo */}
                    <div className={`relative w-8 h-8 rounded-full overflow-hidden flex-shrink-0 ${
                      isSelected ? 'ring-1 ring-tavern-gold-500/40 ring-offset-1 ring-offset-tavern-bg-secondary' : ''
                    }`}>
                      <div className="absolute inset-0 rounded-full bg-gradient-to-br from-tavern-gold-500/10 to-transparent pointer-events-none" />
                      {char.avatar_path ? (
                        <img src={char.avatar_path} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full bg-tavern-bg-tertiary flex items-center justify-center text-xs font-medium text-tavern-text-secondary">
                          {char.name.charAt(0)}
                        </div>
                      )}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className={`text-sm truncate ${
                        isSelected ? 'text-tavern-gold-300' : 'text-tavern-text-primary'
                      }`}>
                        {char.name}
                      </div>
                      <div className="text-[10px] text-tavern-text-muted truncate">
                        {char.description ? char.description.slice(0, 20) : '未设定描述'}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Sessions section - 对话记录 */}
          <div className="flex-1 px-3 py-3 overflow-hidden flex flex-col">
            <div className="flex items-center justify-between mb-2.5 px-1">
              <span className="section-label mb-0">会话记录</span>
              <button
                onClick={handleNewChat}
                className="btn-icon p-1"
                title="新建对话"
              >
                <Plus size={14} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-0.5 scrollbar-thin pr-0.5">
              {!selectedCharacter && (
                <p className="text-xs text-tavern-text-muted text-center py-4">
                  请先选择角色
                </p>
              )}
              {selectedCharacter && sessions.length === 0 && (
                <p className="text-xs text-tavern-text-muted text-center py-4">
                  暂无会话
                </p>
              )}
              {sessions.map((session) => {
                const isActive = currentSession?.id === session.id
                return (
                  <div key={session.id} className="relative group/session">
                    <button
                      onClick={() => { void selectSession(session); navigate('/chat'); closeMobileSidebar() }}
                      className={`w-full flex items-center justify-between gap-2 pl-2.5 pr-8 py-1.5 rounded-lg text-left text-xs transition-all duration-200 ${
                        isActive ? 'bg-tavern-bg-tertiary/50 text-tavern-gold-300' : 'text-tavern-text-secondary hover:bg-tavern-bg-tertiary/30 hover:text-tavern-text-primary'
                      }`}
                    >
                      <span className="truncate flex-1">{session.title}</span>
                      <span className="text-[10px] text-tavern-text-muted flex-shrink-0">{formatTime(session.updated_at)}</span>
                    </button>
                    <button aria-label="会话菜单" className="absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded opacity-60 hover:opacity-100 hover:bg-tavern-bg-tertiary" onClick={(event) => { event.stopPropagation(); setSessionMenuId(sessionMenuId === session.id ? null : session.id) }}><MoreHorizontal size={13}/></button>
                    {sessionMenuId === session.id ? <div className="absolute right-1 top-8 z-50 min-w-28 rounded-lg border border-tavern-border-subtle bg-tavern-bg-secondary shadow-xl p-1">
                      <button className="sidebar-item w-full text-xs" onClick={() => { const title = window.prompt('重命名会话', session.title); if (title?.trim()) void renameSession(session.id, title); setSessionMenuId(null) }}><Pencil size={13}/><span>重命名</span></button>
                      <button className="sidebar-item w-full text-xs" onClick={() => void handleExportSession(session)}><Download size={13}/><span>导出会话</span></button>
                      <button className="sidebar-item w-full text-xs text-red-300" onClick={() => { if (window.confirm(`确定删除会话“${session.title}”吗？\n\n该会话中的消息、剧情分支、运行时状态和会话记忆都会删除，无法撤销。`)) void deleteSession(session.id); setSessionMenuId(null) }}><Trash2 size={13}/><span>删除会话</span></button>
                    </div> : null}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Footer navigation */}
          <div className="px-3 py-3 border-t border-tavern-border-subtle space-y-0.5">
            <button onClick={() => setPersonaOpen(true)} className="sidebar-item w-full"><UserRound size={16}/><span>Persona</span></button>
            <button onClick={() => setGroupOpen(true)} className="sidebar-item w-full"><Users size={16}/><span>多角色编组</span></button>
            <button onClick={() => setBranchOpen(true)} className="sidebar-item w-full"><GitBranch size={16}/><span>剧情分支</span></button>
            <Link to="/memory" className="sidebar-item"><Brain size={16}/><span>长期记忆</span></Link>
            <Link data-testid="open-settings" to="/settings" className="sidebar-item"><Settings size={16}/><span>设置</span></Link>
          </div>
        </div>
      </div>

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/60 z-30 backdrop-blur-sm animate-fade-in"
          onClick={toggleSidebar}
        />
      )}
      <PersonaManager open={personaOpen} onClose={() => setPersonaOpen(false)}/>
      <GroupManager open={groupOpen} onClose={() => setGroupOpen(false)}/>
      <BranchManager open={branchOpen} onClose={() => setBranchOpen(false)}/>
    </>
  )
}
