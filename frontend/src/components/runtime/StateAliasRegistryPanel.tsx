import { useEffect, useMemo, useState } from 'react'
import { Check, Link2, Plus, RefreshCcw, Trash2 } from 'lucide-react'
import {
  confirmCharacterStateAlias,
  deleteCharacterStateAlias,
  getCharacterStateAliases,
} from '@/api'
import type {
  CharacterStateAliasRegistry,
  CharacterStateAliasSuggestion,
} from '@/types'

const readablePath = (path: string) => path
  .split('/')
  .filter(Boolean)
  .map((part) => decodeURIComponent(part.replace(/~1/g, '/').replace(/~0/g, '~')))
  .join(' › ')

const confidenceLabel = (value: number) => `${Math.round(Math.max(0, Math.min(1, value || 0)) * 100)}%`

export default function StateAliasRegistryPanel({ characterId }: { characterId: string }) {
  const [registry, setRegistry] = useState<CharacterStateAliasRegistry | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [alias, setAlias] = useState('')
  const [semantic, setSemantic] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await getCharacterStateAliases(characterId)
      setRegistry(response.data)
      setSemantic((current) => current || response.data.targets[0]?.semantic || '')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法读取角色卡别名')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setRegistry(null)
    setAlias('')
    setSemantic('')
    void load()
    // load is intentionally scoped to the current character.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [characterId])

  const suggestions = useMemo(() => {
    const values = registry?.suggestions || []
    return [...values]
      .sort((left, right) => Number(Boolean(right.observed)) - Number(Boolean(left.observed)) || right.confidence - left.confidence)
      .slice(0, 18)
  }, [registry])

  const confirm = async (candidate?: CharacterStateAliasSuggestion) => {
    const nextAlias = candidate?.alias || alias.trim()
    const nextSemantic = candidate?.semantic || semantic
    if (!nextAlias || !nextSemantic || loading) return
    setLoading(true)
    setError('')
    try {
      const response = await confirmCharacterStateAlias(characterId, {
        alias: nextAlias,
        semantic: nextSemantic,
      })
      setRegistry(response.data)
      setAlias('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '确认别名失败')
    } finally {
      setLoading(false)
    }
  }

  const remove = async (aliasId: string) => {
    if (loading) return
    setLoading(true)
    setError('')
    try {
      const response = await deleteCharacterStateAlias(characterId, aliasId)
      setRegistry(response.data)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除别名失败')
    } finally {
      setLoading(false)
    }
  }

  if (!registry && loading) {
    return <section className="runtime-card state-alias-card"><div className="runtime-section-title"><RefreshCcw size={15}/><span>Card-scoped Alias Registry</span></div><p>正在读取角色卡别名…</p></section>
  }
  if (!registry) return null

  return (
    <details className="runtime-card state-alias-card">
      <summary className="runtime-section-title">
        <Link2 size={15}/><span>Card-scoped Alias Registry</span>
        <span className="tag ml-auto">{registry.summary.confirmed_count || 0} 个已确认</span>
      </summary>

      <p className="state-alias-intro">别名只在当前角色卡生效。候选项不会自动改写状态，必须确认后才进入运行时。</p>

      <div className="state-alias-form">
        <input
          value={alias}
          onChange={(event) => setAlias(event.target.value)}
          placeholder="输入字段别名，例如 favor"
          maxLength={80}
          aria-label="字段别名"
        />
        <select value={semantic} onChange={(event) => setSemantic(event.target.value)} aria-label="目标语义">
          {registry.targets.map((target) => (
            <option key={target.semantic} value={target.semantic}>{target.semantic}</option>
          ))}
        </select>
        <button onClick={() => void confirm()} disabled={!alias.trim() || !semantic || loading}>
          <Plus size={13}/>确认
        </button>
      </div>

      {error ? <p className="state-alias-error">{error}</p> : null}

      <div className="state-alias-section">
        <h4>已确认别名</h4>
        {registry.confirmed.length ? <div className="state-alias-list">
          {registry.confirmed.map((item) => (
            <div className="state-alias-row is-confirmed" key={item.id}>
              <Check size={13}/>
              <div>
                <strong>{item.alias}</strong>
                <small>{item.semantic}</small>
                <code>{readablePath(item.canonical_path)}</code>
              </div>
              <button aria-label={`删除别名 ${item.alias}`} onClick={() => void remove(item.id)} disabled={loading}><Trash2 size={13}/></button>
            </div>
          ))}
        </div> : <p className="state-alias-empty">尚未确认任何别名。</p>}
      </div>

      <div className="state-alias-section">
        <h4>候选映射 <small>{registry.summary.suggestion_count || suggestions.length} 项</small></h4>
        <div className="state-alias-list">
          {suggestions.map((item) => (
            <div className={`state-alias-row ${item.observed ? 'is-observed' : ''}`} key={item.id}>
              <Link2 size={13}/>
              <div>
                <strong>{item.alias}</strong>
                <small>{item.semantic} · 置信度 {confidenceLabel(item.confidence)}</small>
                <code>{readablePath(item.canonical_path)}</code>
                {item.observed_paths?.length ? <small>历史未解析路径：{item.observed_paths.map(readablePath).join('；')}</small> : null}
              </div>
              <button onClick={() => void confirm(item)} disabled={loading}><Check size={13}/>确认</button>
            </div>
          ))}
        </div>
      </div>
    </details>
  )
}
