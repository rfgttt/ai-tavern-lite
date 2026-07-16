import type { CardUIManifest, CardUIManifestPanel, RuntimeState } from '@/types'

const resolvePointer = (state: RuntimeState, pointer: string): unknown => {
  if (!pointer || pointer === '/') return state
  return pointer.split('/').filter(Boolean).reduce<unknown>((current, part) => {
    if (current == null || typeof current !== 'object') return undefined
    return (current as Record<string, unknown>)[part.replace(/~1/g, '/').replace(/~0/g, '~')]
  }, state)
}

const PanelValue = ({ panel, value }: { panel: CardUIManifestPanel; value: unknown }) => {
  if (panel.component === 'progress' && typeof value === 'number') {
    const max = panel.max || 100
    const percent = Math.max(0, Math.min(100, (value / max) * 100))
    return <div><div className="flex justify-between text-xs"><span>{value}</span><span>{max}</span></div><div className="runtime-progress"><i style={{ width: `${percent}%` }}/></div></div>
  }
  if (panel.component === 'tag') return <span className="tag tag-gold">{String(value ?? '—')}</span>
  if (panel.component === 'key-value' || panel.component === 'stat-grid') {
    const entries = value && typeof value === 'object' ? Object.entries(value as Record<string, unknown>) : []
    return <div className="manifest-grid">{entries.slice(0, 24).map(([key, item]) => <div key={key}><span>{key}</span><strong>{typeof item === 'object' ? JSON.stringify(item) : String(item ?? '—')}</strong></div>)}</div>
  }
  return <pre className="manifest-pre">{typeof value === 'string' ? value : JSON.stringify(value, null, 2)}</pre>
}

export default function ManifestPanel({ manifest, state }: { manifest: CardUIManifest | null | undefined; state: RuntimeState }) {
  const panels = manifest?.panels?.filter((panel) => !panel.placement || panel.placement === 'sidebar') || []
  if (!panels.length) return null
  return <>{panels.map((panel) => <section className="runtime-card" key={panel.id}><div className="runtime-section-title"><span>{panel.title || panel.id}</span><span className="tag ml-auto">{panel.component}</span></div><PanelValue panel={panel} value={resolvePointer(state, panel.source)}/></section>)}</>
}
