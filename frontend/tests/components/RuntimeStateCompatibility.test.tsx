import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import InlineCardState from '@/components/messages/InlineCardState'
import CardStateSections from '@/components/runtime/CardStateSections'
import RelationshipStatus from '@/components/runtime/RelationshipStatus'
import { sanitizedCustom } from '@/components/runtime/runtimePresentation'

describe('Tavern MVU native state presentation', () => {
  it('shows card-declared initial relationship values before the first update', () => {
    render(
      <RelationshipStatus
        declared
        timeline={[]}
        relationship={{ affection: 5, fear: 95, dependence: 100 }}
        initialRelationship={{ affection: 5, fear: 95, dependence: 100 }}
      />,
    )

    expect(screen.getByText('角色卡初始状态')).toBeInTheDocument()
    expect(screen.getByText('好感')).toBeInTheDocument()
    expect(screen.getByText('害怕值')).toBeInTheDocument()
    expect(screen.getByText('依赖值')).toBeInTheDocument()
    expect(screen.getByText('95')).toBeInTheDocument()
  })

  it('unwraps MVU value-description tuples and hides schema metadata', () => {
    const presented = sanitizedCustom({
      $meta: { strictSet: true },
      世界信息: { 日期: ['2024年11月9日', '当前日期'] },
      穗秋生: {
        好感度: [5, '[0-100]爱意程度'],
        身上的伤: [['$__META_EXTENSIBLE__$', '额头淤青'], '身体伤势列表'],
        重要记忆: [['$__META_EXTENSIBLE__$'], '发生重要事件时记录'],
      },
    })

    expect(presented).toEqual({
      世界信息: { 日期: '2024年11月9日' },
      穗秋生: { 好感度: 5, 身上的伤: ['额头淤青'] },
    })
  })

  it('renders initial card injuries and memories instead of hiding unchanged state', () => {
    const state = {
      character: {
        name: '穗秋生',
        injuries: ['额头淤青'],
        important_memories: ['第一次被温柔安慰'],
      },
      custom: {
        穗秋生: {
          身上的伤: [['额头淤青'], '身体伤势列表'],
          重要记忆: [['第一次被温柔安慰'], '发生重要事件时记录'],
        },
      },
    }

    render(<CardStateSections state={state} initialState={state} timeline={[]}/>)

    expect(screen.getByText('角色状态')).toBeInTheDocument()
    expect(screen.getAllByText('角色卡初始状态').length).toBeGreaterThan(0)
    expect(screen.getAllByText('身上的伤').length).toBeGreaterThan(0)
    expect(screen.getAllByText('重要记忆').length).toBeGreaterThan(0)
    expect(screen.getAllByText('额头淤青').length).toBeGreaterThan(0)
    expect(screen.getAllByText('第一次被温柔安慰').length).toBeGreaterThan(0)
    expect(screen.getByText('角色卡变量')).toBeInTheDocument()
  })

  it('safely recreates the card status panel with injury tags and paged memories', () => {
    render(<InlineCardState state={{
      scene: { date: '2024年11月9日', time: '16:00', location: '老旧住宅区的家中' },
      relationship: { affection: 8, fear: 92, dependence: 100 },
      character: {
        name: '穗秋生',
        injuries: ['额头有撞击的淤青'],
        important_memories: ['第一次被温柔安慰', '第一次被带去医院治疗'],
      },
    }}/>)

    expect(screen.getByText('穗秋生 · 状态栏')).toBeInTheDocument()
    expect(screen.getByText('原生安全还原 · 不执行卡片脚本')).toBeInTheDocument()
    expect(screen.getByText('2024年11月9日')).toBeInTheDocument()
    expect(screen.getByText('额头有撞击的淤青')).toBeInTheDocument()
    expect(screen.getByText('第一次被温柔安慰')).toBeInTheDocument()
    expect(screen.getByText('1 / 2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '下一条记忆' }))
    expect(screen.getByText('第一次被带去医院治疗')).toBeInTheDocument()
    expect(screen.getByText('2 / 2')).toBeInTheDocument()
  })

})
