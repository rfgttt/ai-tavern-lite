import { AlertTriangle, Braces, CheckCircle2, LockKeyhole } from 'lucide-react'
import type { RuntimeSchemaValidation, RuntimeStateSchema, RuntimeStateSchemaField } from '@/types'

const readablePath = (path: string) => path
  .split('/')
  .filter(Boolean)
  .map((part) => decodeURIComponent(part.replace(/~1/g, '/').replace(/~0/g, '~')))
  .join(' › ')

const fieldRange = (field: RuntimeStateSchemaField) => {
  if (field.minimum === undefined && field.maximum === undefined) return ''
  return `${field.minimum ?? '−∞'}…${field.maximum ?? '+∞'}`
}

const typeLabel = (field: RuntimeStateSchemaField) => {
  if (field.type === 'array' && field.items_type) return `array<${field.items_type}>`
  return field.type || 'any'
}

export default function StateSchemaPanel({
  schema,
  validation,
}: {
  schema?: RuntimeStateSchema
  validation?: RuntimeSchemaValidation
}) {
  if (!schema?.fields) return null
  const summary = schema.summary || {}
  const fields = Object.values(schema.fields)
    .filter((field) => field?.path && !field.path.includes('/$meta'))
    .sort((left, right) => {
      const sourceRank = (field: RuntimeStateSchemaField) => field.source === 'card_initial_variables' ? 0 : field.semantic ? 1 : 2
      return sourceRank(left) - sourceRank(right) || left.path.localeCompare(right.path, 'zh-CN')
    })
  const issues = [...(validation?.errors || []), ...(validation?.warnings || [])]

  return (
    <details className="runtime-card state-schema-card">
      <summary className="runtime-section-title">
        <Braces size={15}/><span>Formal State Schema</span>
        <span className={`tag ml-auto ${validation?.valid === false ? 'is-warning' : ''}`}>
          {validation?.valid === false ? `${validation.error_count} 项错误` : `${summary.field_count || fields.length} 个字段`}
        </span>
      </summary>
      <div className="state-schema-summary">
        <span><b>{summary.declared_count || 0}</b><small>已声明</small></span>
        <span><b>{summary.numeric_count || 0}</b><small>数值字段</small></span>
        <span><b>{summary.constrained_count || 0}</b><small>范围约束</small></span>
        <span><b>{summary.strict_container_count || 0}</b><small>严格容器</small></span>
      </div>

      <div className={`state-schema-validation ${validation?.valid === false ? 'is-invalid' : 'is-valid'}`}>
        {validation?.valid === false ? <AlertTriangle size={13}/> : <CheckCircle2 size={13}/>}
        <span>{validation?.valid === false ? '当前状态未通过 Schema 校验' : '当前状态与 Schema 一致'}</span>
        {validation?.warning_count ? <small>{validation.warning_count} 项兼容性提示</small> : null}
      </div>

      {issues.length ? <div className="state-schema-issues">
        {issues.slice(0, 8).map((issue, index) => (
          <span key={`${issue.path || 'issue'}-${index}`}>
            <code>{issue.code || 'SCHEMA_NOTICE'}</code>
            <b>{readablePath(String(issue.path || '')) || '状态根节点'}</b>
            <small>{issue.message || '未提供说明'}</small>
          </span>
        ))}
      </div> : null}

      <div className="state-schema-fields">
        {fields.map((field) => (
          <div className="state-schema-field" key={field.path}>
            <div>
              <strong>{readablePath(field.path)}</strong>
              <small>{[
                field.semantic || field.description || (field.declared ? '声明字段' : '运行时兼容字段'),
                field.semantic_role === 'projection' && field.canonical_path
                  ? `投影写入 → ${readablePath(field.canonical_path)}`
                  : '',
              ].filter(Boolean).join(' · ')}</small>
            </div>
            <span className="state-schema-field__type">{typeLabel(field)}</span>
            {fieldRange(field) ? <span className="state-schema-field__range">{fieldRange(field)}</span> : null}
            {!field.mutable ? <LockKeyhole size={12}/> : null}
            <small className="state-schema-field__ops">{field.update_modes?.join(' · ') || '只读'}</small>
          </div>
        ))}
      </div>
    </details>
  )
}
