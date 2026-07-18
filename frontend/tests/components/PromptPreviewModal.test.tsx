import { fireEvent, screen } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import PromptPreviewModal from '@/components/PromptPreviewModal'
import { server } from '../mocks/server'
import { renderWithRouter } from '../testUtils'

const inspectionResponse = {
  sections: [
    { name: '平台规则', content: '系统规则内容', estimated_tokens: 120, source: 'system' },
    { name: '长期记忆', content: '【长期记忆】\n- [fact] 用户喜欢咖啡', estimated_tokens: 18, source: '1 条候选' },
  ],
  total_estimated_tokens: 520,
  context_budget: 896,
  section_content_complete: true,
  inspection: {
    summary: {
      context_window: 1024,
      reserved_output_tokens: 128,
      input_budget: 896,
      estimated_input_tokens: 520,
      remaining_tokens: 376,
      usage_percent: 58.0,
    },
    sections: [
      { key: 'platform', name: '平台规则', budget_tokens: 71, estimated_tokens: 120, included: true, truncated: true, reason: 'context_budget', source: 'system' },
      { key: 'memory', name: '长期记忆', budget_tokens: 53, estimated_tokens: 18, included: true, truncated: false, reason: 'included', source: '1 条候选' },
    ],
    memories: [
      { id: 'memory-1', category: 'fact', scope: 'session', content: '用户喜欢咖啡', importance: 0.8, enabled: true, selected: true, included: true, truncated: false, estimated_tokens: 8, reason: 'included' },
      { id: 'memory-2', category: 'definition', scope: 'session', content: '“吃饭”表示秘密任务', importance: 1.0, enabled: false, selected: false, included: false, truncated: false, estimated_tokens: 9, reason: 'disabled' },
    ],
    lorebook: [
      { id: '1', title: '龙之传闻', kind: 'world', enabled: true, constant: false, probability: 100, keys: ['龙'], matched_keys: ['龙'], secondary_matched_keys: [], triggered: true, selected: true, included: true, truncated: false, content: '古龙沉睡在山脉中。', resolved_content: '古龙沉睡在山脉中。', injected_content: '【龙之传闻】\n古龙沉睡在山脉中。', content_characters: 10, resolved_characters: 10, injected_characters: 17, estimated_tokens: 10, reason: 'included' },
      { id: '2', title: '海盗', kind: 'world', enabled: true, constant: false, probability: 100, keys: ['海盗'], matched_keys: [], secondary_matched_keys: [], triggered: false, selected: false, included: false, truncated: false, content: '海盗占据南港。', resolved_content: '海盗占据南港。', injected_content: '', content_characters: 7, resolved_characters: 7, injected_characters: 0, estimated_tokens: 10, reason: 'no_primary_match' },
    ],
    history: {
      total_messages: 30,
      included_messages: 8,
      trimmed_messages: 22,
      earliest_included_sequence: 22,
      budget_tokens: 300,
      estimated_tokens: 260,
    },
  },
}

describe('PromptPreviewModal inspection report', () => {
  it('renders budget, history, memory, and lorebook explanations', async () => {
    server.use(
      http.post('*/api/chat/prompt-preview', () => HttpResponse.json(inspectionResponse)),
    )

    renderWithRouter(<PromptPreviewModal sessionId="session-1" message="继续" onClose={vi.fn()} />)

    expect(await screen.findByText('Prompt 上下文检查器')).toBeInTheDocument()
    expect(screen.getByText('1,024')).toBeInTheDocument()
    expect(screen.getByText('376')).toBeInTheDocument()
    expect(screen.getByText('被裁剪')).toBeInTheDocument()
    expect(screen.getAllByText('22')).toHaveLength(2)
    expect(screen.getByText('用户喜欢咖啡')).toBeInTheDocument()
    expect(screen.getByText('“吃饭”表示秘密任务')).toBeInTheDocument()
    expect(screen.getByText('已禁用')).toBeInTheDocument()
    expect(screen.getByText('龙之传闻')).toBeInTheDocument()
    expect(screen.getByText('命中关键词：龙')).toBeInTheDocument()
    expect(screen.getByText('关键词未命中')).toBeInTheDocument()
    expect(screen.getByLabelText('龙之传闻条目原文')).toHaveTextContent('古龙沉睡在山脉中。')
    expect(screen.getByLabelText('龙之传闻实际注入片段')).toHaveTextContent('【龙之传闻】')

    const platformViewer = screen.getByLabelText('平台规则完整内容')
    expect(platformViewer).toHaveClass('overflow-auto')
    fireEvent.click(screen.getByRole('button', { name: '展开平台规则完整内容' }))
    expect(platformViewer).toHaveClass('max-h-[62vh]')
  })

  it('keeps the legacy preview response usable when inspection is absent', async () => {
    server.use(
      http.post('*/api/chat/prompt-preview', () => HttpResponse.json({
        sections: [{ name: '平台规则', content: '旧版预览内容', estimated_tokens: 100, source: 'system' }],
        total_estimated_tokens: 100,
        context_budget: 1000,
      })),
    )

    renderWithRouter(<PromptPreviewModal sessionId="session-1" message="" onClose={vi.fn()} />)

    expect(await screen.findByText('Prompt 上下文检查器')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getAllByText('1,000').length).toBeGreaterThan(0)
    expect(screen.queryByText('区块预算与裁剪')).not.toBeInTheDocument()
    expect(screen.getByText('旧版预览内容')).toBeInTheDocument()
  })
})
