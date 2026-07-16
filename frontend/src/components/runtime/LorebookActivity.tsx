import { BookMarked, ChevronRight } from 'lucide-react'
import type { LorebookTrigger } from '@/types'

const positionLabel = (value?: string) => {
  const labels: Record<string, string> = {
    before_char: '角色设定之前', after_char: '角色设定之后', before_an: '作者注释之前',
    after_an: '作者注释之后', at_depth: '聊天深度插入', before_example: '示例对话之前',
    after_example: '示例对话之后',
  }
  return labels[value || ''] || value || '默认位置'
}

export default function LorebookActivity({ entries, total }: { entries: LorebookTrigger[]; total: number }) {
  if (!total && !entries.length) return null
  return (
    <section className="runtime-card">
      <div className="runtime-section-title">
        <BookMarked size={15}/><span>本轮触发世界书</span>
        <span className="tag ml-auto">{entries.length}/{total}</span>
      </div>
      {entries.length ? (
        <div className="runtime-lore-list">
          {entries.slice(0, 10).map((entry, index) => {
            const title = entry.title || entry.comment || entry.keys?.join('、') || `未命名条目 #${entry.id ?? index + 1}`
            return (
              <details key={`${entry.id ?? index}-${title}`} className="runtime-lore-entry">
                <summary>
                  <ChevronRight size={12}/>
                  <span><strong>{title}</strong><small>{entry.keys?.length ? `触发词：${entry.keys.join('、')}` : '常驻或递归触发'}</small></span>
                  <i className="runtime-lore-status">已注入</i>
                </summary>
                <div>
                  <p><b>插入位置：</b>{positionLabel(entry.position)}</p>
                  {entry.content_preview ? <p><b>内容摘要：</b>{entry.content_preview}</p> : <p>该条目未提供可显示摘要。</p>}
                </div>
              </details>
            )
          })}
        </div>
      ) : (
        <p className="runtime-empty">角色卡包含 {total} 条世界书设定，但本轮没有条目被触发。</p>
      )}
    </section>
  )
}
