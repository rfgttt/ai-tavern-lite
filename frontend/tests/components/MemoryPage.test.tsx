import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'

import MemoryPage from '@/pages/MemoryPage'
import { useAppStore } from '@/stores/appStore'
import type { Memory } from '@/types'
import { charactersFixture, sessionsFixture } from '../mocks/fixtures'
import { server } from '../mocks/server'
import { renderWithRouter, resetAppStore } from '../testUtils'

const memoryFixture: Memory = {
  id: 'memory-global',
  character_id: null,
  session_id: null,
  category: 'general',
  content: '全局测试记忆',
  importance: 0.5,
  keywords: '',
  enabled: true,
  created_at: '2026-07-18T00:00:00Z',
  updated_at: '2026-07-18T00:00:00Z',
}

describe('MemoryPage scope handling', () => {
  beforeEach(() => {
    resetAppStore()
    useAppStore.setState({
      selectedCharacter: charactersFixture[0],
      currentSession: sessionsFixture[0],
    })
  })

  it('loads the effective context and creates session memory with both ids', async () => {
    const listRequests: URL[] = []
    let createdBody: Record<string, unknown> | null = null

    server.use(
      http.get('*/api/memories', ({ request }) => {
        listRequests.push(new URL(request.url))
        return HttpResponse.json([memoryFixture])
      }),
      http.post('*/api/memories', async ({ request }) => {
        createdBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({
          ...memoryFixture,
          id: 'memory-session',
          content: String(createdBody.content),
          character_id: String(createdBody.character_id),
          session_id: String(createdBody.session_id),
        })
      }),
    )

    renderWithRouter(<MemoryPage />)

    await screen.findByText('全局测试记忆')
    expect(listRequests[0].searchParams.get('scope')).toBe('effective')
    expect(listRequests[0].searchParams.get('character_id')).toBe('character-linya')
    expect(listRequests[0].searchParams.get('session_id')).toBe('session-linya-1')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '添加记忆' }))
    expect(screen.getByLabelText('作用范围')).toHaveValue('session')
    await user.type(screen.getByLabelText('记忆内容'), '当前会话中的秘密')
    await user.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(createdBody).not.toBeNull())
    expect(createdBody).toMatchObject({
      content: '当前会话中的秘密',
      character_id: 'character-linya',
      session_id: 'session-linya-1',
    })
  })

  it('requests an exact global scope when the scope filter changes', async () => {
    const listRequests: URL[] = []
    server.use(
      http.get('*/api/memories', ({ request }) => {
        listRequests.push(new URL(request.url))
        return HttpResponse.json([memoryFixture])
      }),
    )

    renderWithRouter(<MemoryPage />)
    await screen.findByText('全局测试记忆')

    const user = userEvent.setup()
    await user.selectOptions(screen.getByDisplayValue('当前上下文'), 'global')

    await waitFor(() => {
      expect(listRequests.some((url) => url.searchParams.get('scope') === 'global')).toBe(true)
    })
  })
})

describe('MemoryPage duplicate handling', () => {
  beforeEach(() => {
    resetAppStore()
    useAppStore.setState({
      selectedCharacter: charactersFixture[0],
      currentSession: sessionsFixture[0],
    })
  })

  it('warns on an exact duplicate and only forces creation after explicit confirmation', async () => {
    const existingMemory: Memory = {
      ...memoryFixture,
      id: 'memory-existing',
      character_id: 'character-linya',
      session_id: 'session-linya-1',
      category: 'fact',
      content: '用户住在北京',
    }
    const postBodies: Record<string, unknown>[] = []

    server.use(
      http.get('*/api/memories', () => HttpResponse.json([existingMemory])),
      http.post('*/api/memories', async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        postBodies.push(body)
        if (body.allow_duplicate !== true) {
          return HttpResponse.json({
            detail: {
              code: 'memory_duplicate',
              message: '当前作用域和分类中已存在内容相同的记忆（已启用）',
              memory_id: existingMemory.id,
              enabled: true,
              category: 'fact',
              scope: 'session',
            },
          }, { status: 409 })
        }
        return HttpResponse.json({ ...existingMemory, id: 'memory-forced-copy' })
      }),
    )

    renderWithRouter(<MemoryPage />)
    await screen.findByText('用户住在北京')

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '添加记忆' }))
    await user.selectOptions(screen.getByLabelText('分类'), 'fact')
    await user.type(screen.getByLabelText('记忆内容'), '用户住在北京')
    await user.click(screen.getByRole('button', { name: '保存' }))

    expect(await screen.findByText('当前作用域和分类中已存在内容相同的记忆（已启用）')).toBeInTheDocument()
    expect(screen.getByText('系统没有删除或修改已有记忆。你可以查看旧记录，或明确保留一条完全相同的新记录。')).toBeInTheDocument()
    expect(postBodies).toHaveLength(1)
    expect(postBodies[0].allow_duplicate).toBe(false)

    await user.click(screen.getByRole('button', { name: '仍然保存' }))

    await waitFor(() => expect(postBodies).toHaveLength(2))
    expect(postBodies[1].allow_duplicate).toBe(true)
    await waitFor(() => expect(screen.queryByText('当前作用域和分类中已存在内容相同的记忆（已启用）')).not.toBeInTheDocument())
  })

  it('offers the definition category and treats legacy user_fact as fact when editing', async () => {
    const legacyMemory: Memory = {
      ...memoryFixture,
      id: 'memory-legacy-fact',
      category: 'user_fact',
      content: '用户叫小明',
    }
    server.use(
      http.get('*/api/memories', () => HttpResponse.json([legacyMemory])),
    )

    renderWithRouter(<MemoryPage />)
    await screen.findByText('用户叫小明')
    expect(screen.getAllByText('事实').length).toBeGreaterThan(0)

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '添加记忆' }))
    expect(screen.getAllByRole('option', { name: '定义' }).length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: '取消' }))

    await user.click(screen.getByRole('button', { name: '编辑记忆' }))
    expect(screen.getByLabelText('分类')).toHaveValue('fact')
  })
})
