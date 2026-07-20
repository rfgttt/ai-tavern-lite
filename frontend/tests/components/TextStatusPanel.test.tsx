import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import StructuredMessage from '@/components/messages/StructuredMessage'
import type { Message } from '@/types'

const message: Message = {
  id: 'status-message',
  session_id: 'session-1',
  role: 'assistant',
  content: '正文',
  sequence: 1,
  generation_status: 'complete',
  segments: [
    { type: 'markdown', text: '正文' },
    { type: 'status-panel-placeholder', artifact_index: 0 },
  ],
  artifacts: [{
    type: 'status-panel',
    data: {
      schema: 'ai-tavern-status-panel/1',
      protocol: 'text-end',
      title: '剧情状态',
      sections: [
        {
          kind: 'environment',
          title: '环境',
          fields: [
            { icon: '📍', label: '地点', value: '游轮客房' },
            { icon: '🌤️', label: '天气', value: '晴朗' },
          ],
        },
        {
          kind: 'characters',
          title: '角色状态',
          characters: [
            {
              name: '宁仪',
              badge: '🌙',
              fields: [{ label: '心绪', value: '保持警惕' }],
            },
          ],
        },
        {
          kind: 'interaction',
          title: '关系互动',
          text: '气氛微妙',
        },
      ],
    },
  }],
  speaker_metadata: {},
  render_version: 2,
  created_at: '2026-07-20T00:00:00',
  updated_at: '2026-07-20T00:00:00',
}

describe('TextStatusPanel', () => {
  it('renders a parsed text status artifact as native safe UI', () => {
    render(<StructuredMessage message={message}/>)

    expect(screen.getByTestId('text-status-panel')).toBeInTheDocument()
    expect(screen.getByText('剧情状态')).toBeInTheDocument()
    expect(screen.getByText('游轮客房')).toBeInTheDocument()
    expect(screen.getByText('宁仪')).toBeInTheDocument()
    expect(screen.getByText('保持警惕')).toBeInTheDocument()
    expect(screen.getByText('气氛微妙')).toBeInTheDocument()
    expect(screen.queryByText('<text>')).not.toBeInTheDocument()
  })

  it('does not execute or inject source HTML from artifact metadata', () => {
    const unsafe = structuredClone(message)
    const data = unsafe.artifacts?.[0].data as Record<string, unknown>
    data.source_text = '<script>window.__unsafe = true</script>'

    const { container } = render(<StructuredMessage message={unsafe}/>)
    expect(container.querySelector('script')).toBeNull()
    expect((window as Window & { __unsafe?: boolean }).__unsafe).toBeUndefined()
  })
})
