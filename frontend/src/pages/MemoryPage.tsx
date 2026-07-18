import { useState, useEffect } from 'react'
import { getMemories, createMemory, updateMemory, deleteMemory } from '@/api'
import type { MemoryScopeFilter } from '@/api'
import type { Memory } from '@/types'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '@/stores/appStore'
import {
  Plus,
  Edit2,
  Trash2,
  Search,
  Brain,
  X,
  ToggleLeft,
  ToggleRight,
  Bookmark,
} from 'lucide-react'

type MemoryCreateScope = 'character' | 'session' | 'global'

const categoryLabels: Record<string, string> = {
  general: '通用',
  fact: '事实',
  relationship: '关系',
  event: '事件',
  preference: '偏好',
  pending: '待处理',
}

export default function MemoryPage({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate()
  const selectedCharacter = useAppStore((state) => state.selectedCharacter)
  const currentSession = useAppStore((state) => state.currentSession)
  const [memories, setMemories] = useState<Memory[]>([])
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [scopeFilter, setScopeFilter] = useState<MemoryScopeFilter>('effective')
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingMemory, setEditingMemory] = useState<Memory | null>(null)
  const [scope, setScope] = useState<MemoryCreateScope>('character')
  const [formData, setFormData] = useState({
    category: 'general',
    content: '',
    importance: 0.5,
    keywords: '',
    enabled: true,
  })

  const categories = ['general', 'fact', 'relationship', 'event', 'preference', 'pending']

  useEffect(() => {
    if (scopeFilter === 'session' && !currentSession) setScopeFilter('effective')
    if (scopeFilter === 'character' && !selectedCharacter) setScopeFilter('effective')
  }, [scopeFilter, selectedCharacter, currentSession])

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadMemories() }, 250)
    return () => window.clearTimeout(timer)
  }, [search, categoryFilter, scopeFilter, selectedCharacter?.id, currentSession?.id])

  const loadMemories = async () => {
    setLoading(true)
    try {
      const resolvedScope =
        scopeFilter === 'session' && !currentSession
          ? 'effective'
          : scopeFilter === 'character' && !selectedCharacter
            ? 'effective'
            : scopeFilter
      const params: NonNullable<Parameters<typeof getMemories>[0]> = { scope: resolvedScope }
      if (selectedCharacter?.id) params.character_id = selectedCharacter.id
      if (currentSession?.id) params.session_id = currentSession.id
      if (search) params.search = search
      if (categoryFilter) params.category = categoryFilter
      const res = await getMemories(params)
      setMemories(res.data)
    } finally {
      setLoading(false)
    }
  }

  const openAddModal = () => {
    setEditingMemory(null)
    setScope(currentSession ? 'session' : selectedCharacter ? 'character' : 'global')
    setFormData({
      category: 'general',
      content: '',
      importance: 0.5,
      keywords: '',
      enabled: true,
    })
    setShowAddModal(true)
  }

  const openEditModal = (mem: Memory) => {
    setEditingMemory(mem)
    setScope(mem.session_id ? 'session' : mem.character_id ? 'character' : 'global')
    setFormData({
      category: mem.category,
      content: mem.content,
      importance: mem.importance,
      keywords: mem.keywords,
      enabled: mem.enabled,
    })
    setShowAddModal(true)
  }

  const handleSave = async () => {
    try {
      const content = formData.content.trim()
      if (!content) return
      if (editingMemory) {
        await updateMemory(editingMemory.id, { ...formData, content })
      } else {
        await createMemory({
          ...formData,
          content,
          character_id:
            scope === 'global'
              ? null
              : scope === 'session'
                ? currentSession?.character_id ?? selectedCharacter?.id ?? null
                : selectedCharacter?.id ?? null,
          session_id: scope === 'session' ? currentSession?.id ?? null : null,
        })
      }
      setShowAddModal(false)
      loadMemories()
    } catch (err) {
      alert('保存失败')
    }
  }

  const handleDelete = async (id: string) => {
    if (confirm('确定要删除这条记忆吗？')) {
      await deleteMemory(id)
      loadMemories()
    }
  }

  const toggleEnabled = async (mem: Memory) => {
    await updateMemory(mem.id, { enabled: !mem.enabled })
    loadMemories()
  }

  return (
    <div className={`h-full bg-tavern-bg-deepest tavern-bg ${embedded ? 'rounded-2xl' : ''}`}>
      <div className="h-full overflow-y-auto scrollbar-thin">
        <div className="max-w-4xl mx-auto px-6 py-8">
          {embedded ? <button onClick={() => navigate('/chat')} className="fixed sm:absolute top-4 right-4 btn-icon z-10" title="返回对话"><X size={18}/></button> : null}
          {/* Page header */}
          <div className="flex items-center justify-between mb-7">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-tavern-gold-900/30 border border-tavern-border-gold/30 flex items-center justify-center">
                <Brain size={20} className="text-tavern-gold-400" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-tavern-text-primary">长期记忆</h1>
                <p className="text-xs text-tavern-text-muted">全局、角色共享与会话专属记忆严格隔离</p>
              </div>
            </div>
            <button onClick={openAddModal} className="btn btn-primary flex items-center gap-1.5">
              <Plus size={15} />
              添加记忆
            </button>
          </div>

          {/* Filters */}
          <div className="card-parchment mb-5">
            <div className="flex gap-4 flex-wrap">
              <div className="flex-1 min-w-[200px] relative">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-tavern-text-muted" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="搜索记忆内容..."
                  className="input input-search"
                />
              </div>
              <select
                value={scopeFilter}
                onChange={(e) => setScopeFilter(e.target.value as MemoryScopeFilter)}
                className="input w-44"
              >
                <option value="effective">当前上下文</option>
                {currentSession ? <option value="session">仅当前会话</option> : null}
                {selectedCharacter ? <option value="character">仅当前角色共享</option> : null}
                <option value="global">仅全局</option>
              </select>
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="input w-36"
              >
                <option value="">全部分类</option>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {categoryLabels[c] || c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Memory list */}
          {loading ? (
            <div className="text-center py-16">
              <div className="generating-dots justify-center mb-3">
                <span /><span /><span />
              </div>
              <p className="text-sm text-tavern-text-muted">加载中...</p>
            </div>
          ) : memories.length === 0 ? (
            <div className="text-center py-20">
              <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-tavern-bg-tertiary/40 flex items-center justify-center">
                <Bookmark size={28} className="text-tavern-text-muted/60" />
              </div>
              <p className="text-tavern-text-secondary mb-1">暂无记忆</p>
              <p className="text-sm text-tavern-text-muted">点击右上角添加第一条记忆</p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {memories.map((mem, idx) => (
                <div
                  key={mem.id}
                  className="card-parchment flex items-start gap-3.5 animate-slide-up"
                  style={{ animationDelay: `${idx * 30}ms` }}
                >
                  <button
                    onClick={() => toggleEnabled(mem)}
                    className="mt-0.5 text-tavern-text-muted hover:text-tavern-text-primary transition-colors flex-shrink-0"
                  >
                    {mem.enabled ? (
                      <ToggleRight size={22} className="text-tavern-gold-400" />
                    ) : (
                      <ToggleLeft size={22} />
                    )}
                  </button>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="tag text-[10px] px-2 py-0">
                        {categoryLabels[mem.category] || mem.category}
                      </span>
                      <span className="tag text-[10px] px-2 py-0">
                        {mem.session_id ? '会话专属' : mem.character_id ? '角色共享' : '全局'}
                      </span>
                      <span className="text-[11px] text-tavern-text-muted">
                        重要度: {mem.importance.toFixed(1)}
                      </span>
                    </div>
                    <p className={`text-sm leading-relaxed ${mem.enabled ? 'text-tavern-text-primary' : 'text-tavern-text-muted line-through'}`}>
                      {mem.content}
                    </p>
                    {mem.keywords && (
                      <p className="text-[11px] text-tavern-text-muted mt-1.5">
                        关键词: {mem.keywords}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-0.5 flex-shrink-0">
                    <button
                      onClick={() => openEditModal(mem)}
                      className="btn-icon p-1.5"
                    >
                      <Edit2 size={14} />
                    </button>
                    <button
                      onClick={() => handleDelete(mem.id)}
                      className="btn-icon p-1.5 hover:text-tavern-rose-400"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Add/Edit Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-tavern-bg-secondary/95 backdrop-blur-md border border-tavern-border-subtle rounded-2xl w-full max-w-lg shadow-large animate-slide-up">
            <div className="flex items-center justify-between px-5 py-4 border-b border-tavern-border-subtle">
              <h3 className="text-sm font-semibold text-tavern-text-primary">
                {editingMemory ? '编辑记忆' : '添加记忆'}
              </h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="btn-icon p-1.5"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {!editingMemory ? (
                <div>
                  <label htmlFor="memory_scope" className="block text-xs text-tavern-text-secondary mb-1.5 font-medium">作用范围</label>
                  <select id="memory_scope" value={scope} onChange={(event) => setScope(event.target.value as MemoryCreateScope)} className="input">
                    {currentSession ? <option value="session">当前会话（最精确）</option> : null}
                    {selectedCharacter ? <option value="character">当前角色</option> : null}
                    <option value="global">所有角色（谨慎使用）</option>
                  </select>
                </div>
              ) : null}
              <div>
                <label htmlFor="memory_category" className="block text-xs text-tavern-text-secondary mb-1.5 font-medium">分类</label>
                <select
                  id="memory_category"
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                  className="input"
                >
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {categoryLabels[c] || c}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="memory_content" className="block text-xs text-tavern-text-secondary mb-1.5 font-medium">记忆内容</label>
                <textarea
                  id="memory_content"
                  value={formData.content}
                  onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                  className="textarea h-24"
                  placeholder="输入记忆内容..."
                />
              </div>

              <div>
                <label htmlFor="memory_importance" className="block text-xs text-tavern-text-secondary mb-1.5 font-medium">
                  重要度: {formData.importance}
                </label>
                <input
                  id="memory_importance"
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={formData.importance}
                  onChange={(e) =>
                    setFormData({ ...formData, importance: parseFloat(e.target.value) })
                  }
                  className="w-full accent-tavern-gold-500"
                />
              </div>

              <div>
                <label htmlFor="memory_keywords" className="block text-xs text-tavern-text-secondary mb-1.5 font-medium">关键词（逗号分隔）</label>
                <input
                  id="memory_keywords"
                  type="text"
                  value={formData.keywords}
                  onChange={(e) => setFormData({ ...formData, keywords: e.target.value })}
                  className="input"
                  placeholder="关键词1, 关键词2"
                />
              </div>

              <div className="flex items-center gap-2.5">
                <input
                  type="checkbox"
                  id="mem_enabled"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="w-4 h-4 accent-tavern-gold-500"
                />
                <label htmlFor="mem_enabled" className="text-sm text-tavern-text-primary cursor-pointer">启用此记忆</label>
              </div>
            </div>

            <div className="px-5 py-4 border-t border-tavern-border-subtle flex justify-end gap-2.5">
              <button
                onClick={() => setShowAddModal(false)}
                className="btn btn-secondary"
              >
                取消
              </button>
              <button onClick={handleSave} className="btn btn-primary">
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
