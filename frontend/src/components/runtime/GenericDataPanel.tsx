import { Braces, ChevronRight } from 'lucide-react'
import { useState } from 'react'

const isPrimitive = (value: unknown) => value == null || ['string', 'number', 'boolean'].includes(typeof value)

const Primitive = ({ value }: { value: unknown }) => {
  if (typeof value === 'boolean') return <span className={`tag ${value ? 'tag-gold' : ''}`}>{value ? '是' : '否'}</span>
  if (typeof value === 'number') return <strong className="generic-data-number">{value}</strong>
  if (value == null || value === '') return <span className="text-tavern-text-muted">—</span>
  return <span>{String(value)}</span>
}

function DataNode({ name, value, depth = 0 }: { name: string; value: unknown; depth?: number }) {
  const [open, setOpen] = useState(depth < 1)
  if (isPrimitive(value)) return <div className="generic-data-row"><span>{name}</span><Primitive value={value}/></div>

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index + 1), item] as const)
    : Object.entries((value || {}) as Record<string, unknown>)

  return (
    <div className="generic-data-group">
      <button aria-expanded={open} onClick={() => setOpen((current) => !current)}>
        <ChevronRight size={12} className={open ? 'rotate-90' : ''}/><span>{name}</span><small>{entries.length}</small>
      </button>
      {open ? <div className="generic-data-children">{entries.slice(0, 80).map(([key, item]) => <DataNode key={key} name={key} value={item} depth={depth + 1}/>)}</div> : null}
    </div>
  )
}

export default function GenericDataPanel({
  value,
  title = '卡片状态',
  subtitle,
  icon = <Braces size={15}/>,
  developer = false,
}: {
  value: unknown
  title?: string
  subtitle?: string
  icon?: React.ReactNode
  developer?: boolean
}) {
  const empty = value == null || (typeof value === 'object' && Object.keys(value as object).length === 0)
  if (empty) return null
  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index + 1), item] as const)
    : typeof value === 'object'
      ? Object.entries(value as Record<string, unknown>)
      : [['值', value] as const]
  return (
    <section data-testid="generic-data-panel" className={`runtime-card ${developer ? 'runtime-developer-card' : ''}`}>
      <div className="runtime-section-title">{icon}<span>{title}</span>{subtitle ? <span className="tag ml-auto">{subtitle}</span> : null}</div>
      <div className="generic-data-root">{entries.slice(0, 100).map(([key, item]) => <DataNode key={key} name={key} value={item}/>)}</div>
    </section>
  )
}
