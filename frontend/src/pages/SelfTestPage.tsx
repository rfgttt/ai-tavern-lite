import { useEffect, useMemo, useRef, useState } from 'react'
import StructuredMessage from '@/components/messages/StructuredMessage'
import GenericDataPanel from '@/components/runtime/GenericDataPanel'
import type { Message } from '@/types'
import { submitSelfTestFrontend } from '@/api'

type TestStatus = 'passed' | 'failed' | 'running'

interface TestResult {
  name: string
  status: TestStatus
  duration_ms: number
  detail?: string
  error?: string
}

interface TestHookSnapshot {
  selectedCharacterId: string | null
  currentSessionId: string | null
  messageCount: number
  loadingMessages: boolean
  messageLoadError: string | null
  draft: string
  scrollPosition: number
}

interface TestHook {
  prepare: (characterId: string, sessionId: string) => Promise<TestHookSnapshot>
  snapshot: () => TestHookSnapshot
  setDraft: (sessionId: string, value: string) => void
  setScrollPosition: (sessionId: string, value: number) => void
}

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

async function waitFor<T>(reader: () => T | null | undefined, timeoutMs = 15000): Promise<T> {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const value = reader()
    if (value) return value
    await sleep(100)
  }
  throw new Error(`等待超时（${timeoutMs}ms）`)
}

const syntheticMessage: Message = {
  id: 'self-test-message',
  session_id: 'self-test',
  role: 'assistant',
  content: '艾琳：“保持警惕。”\n\n莉亚：“我来检查前方。”',
  sequence: 0,
  generation_status: 'complete',
  segments: [
    { type: 'dialogue', speaker: '艾琳', text: '保持警惕。', emotion: '警觉' },
    { type: 'dialogue', speaker: '莉亚', text: '我来检查前方。', emotion: '专注' },
  ],
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

export default function SelfTestPage() {
  const params = useMemo(() => new URLSearchParams(window.location.search), [])
  const runId = params.get('run_id') || ''
  const characterId = params.get('character_id') || ''
  const sessionId = params.get('session_id') || ''
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const speakerProbeRef = useRef<HTMLDivElement>(null)
  const dataProbeRef = useRef<HTMLDivElement>(null)
  const [results, setResults] = useState<TestResult[]>([])
  const [finished, setFinished] = useState(false)
  const [overall, setOverall] = useState<TestStatus>('running')

  useEffect(() => {
    let cancelled = false

    const run = async () => {
      const collected: TestResult[] = []
      const execute = async (name: string, action: () => Promise<string | void> | string | void) => {
        const started = performance.now()
        try {
          const detail = await action()
          const item: TestResult = {
            name,
            status: 'passed',
            duration_ms: Math.round(performance.now() - started),
            detail: detail || undefined,
          }
          collected.push(item)
          if (!cancelled) setResults([...collected])
        } catch (error) {
          const item: TestResult = {
            name,
            status: 'failed',
            duration_ms: Math.round(performance.now() - started),
            error: error instanceof Error ? error.message : String(error),
          }
          collected.push(item)
          if (!cancelled) setResults([...collected])
        }
      }

      await execute('前端自检参数', () => {
        if (!runId || !characterId || !sessionId) throw new Error('缺少 run_id、character_id 或 session_id')
        return `run=${runId}`
      })

      let hook: TestHook | null = null
      await execute('实际应用 iframe 加载', async () => {
        const iframe = await waitFor(() => iframeRef.current)
        const win = await waitFor(() => iframe.contentWindow)
        hook = await waitFor(() => (win as Window & { __AI_TAVERN_TEST__?: TestHook }).__AI_TAVERN_TEST__, 20000)
        return '应用测试钩子已就绪'
      })

      await execute('会话载入与消息持久化', async () => {
        if (!hook) throw new Error('应用测试钩子不可用')
        const snapshot = await hook.prepare(characterId, sessionId)
        if (snapshot.currentSessionId !== sessionId) throw new Error(`当前会话错误：${snapshot.currentSessionId}`)
        if (snapshot.messageCount < 2) throw new Error(`消息数量过少：${snapshot.messageCount}`)
        if (snapshot.loadingMessages) throw new Error('消息仍处于加载状态')
        if (snapshot.messageLoadError) throw new Error(snapshot.messageLoadError)
        return `${snapshot.messageCount} 条消息`
      })

      await execute('会话管理菜单可用', async () => {
        const iframe = iframeRef.current
        if (!iframe?.contentDocument) throw new Error('无法读取应用 iframe 文档')
        const menuButton = await waitFor(() => iframe.contentDocument?.querySelector('[data-testid="session-menu-button"]') as HTMLButtonElement | null)
        menuButton.click()
        await waitFor(() => Array.from(iframe.contentDocument?.querySelectorAll('button') || []).find((button) => button.textContent?.includes('删除会话')))
        const menuText = iframe.contentDocument.body.textContent || ''
        for (const label of ['重命名', '导出会话', '删除会话']) {
          if (!menuText.includes(label)) throw new Error(`会话菜单缺少：${label}`)
        }
        menuButton.click()
        return '重命名、导出和删除入口均可见'
      })

      await execute('卡片驱动面板不显示假占位值', async () => {
        const iframe = iframeRef.current
        if (!iframe?.contentDocument) throw new Error('无法读取应用 iframe 文档')
        const panel = await waitFor(() => {
          const candidate = iframe.contentDocument?.querySelector('.runtime-panel') as HTMLElement | null
          return candidate?.textContent?.includes('角色卡兼容情况') && candidate.textContent.includes('自检世界书') ? candidate : null
        }, 20000)
        const content = panel.textContent || ''
        for (const forbidden of ['环境平稳', '周围平静', '未命名场景']) {
          if (content.includes(forbidden)) throw new Error(`仍显示平台假占位：${forbidden}`)
        }
        if (content.includes('任务与线索')) throw new Error('空任务面板仍然显示')
        if (!content.includes('角色卡兼容情况')) throw new Error('缺少人类可读兼容报告')
        if (!content.includes('自检世界书')) throw new Error('世界书没有显示真实条目名称')
        return '空面板已隐藏，场景/兼容/世界书使用真实数据'
      })

      const draftValue = `self-test-draft-${Date.now()}`
      const scrollValue = 37
      await execute('草稿与滚动位置写入', async () => {
        if (!hook) throw new Error('应用测试钩子不可用')
        const iframe = iframeRef.current
        if (!iframe?.contentDocument || !iframe.contentWindow) throw new Error('无法读取应用 iframe')
        const textarea = await waitFor(() => iframe.contentDocument?.querySelector('[data-testid="chat-composer"]') as HTMLTextAreaElement | null)
        const frameGlobals = iframe.contentWindow as unknown as { HTMLTextAreaElement: typeof HTMLTextAreaElement; Event: typeof Event }
        const setter = Object.getOwnPropertyDescriptor(frameGlobals.HTMLTextAreaElement.prototype, 'value')?.set
        if (!setter) throw new Error('无法写入输入框')
        setter.call(textarea, draftValue)
        textarea.dispatchEvent(new frameGlobals.Event('input', { bubbles: true }))
        const messageList = await waitFor(() => iframe.contentDocument?.querySelector('[data-testid="message-list"]') as HTMLElement | null)
        messageList.scrollTop = scrollValue
        messageList.dispatchEvent(new frameGlobals.Event('scroll', { bubbles: true }))
        await sleep(150)
        const snapshot = hook.snapshot()
        if (snapshot.draft !== draftValue) throw new Error('草稿未写入缓存')
        if (snapshot.scrollPosition !== scrollValue) throw new Error(`滚动位置未写入缓存：${snapshot.scrollPosition}`)
      })

      await execute('设置覆盖层不卸载聊天', async () => {
        if (!hook) throw new Error('应用测试钩子不可用')
        const iframe = iframeRef.current
        if (!iframe?.contentDocument) throw new Error('无法读取应用 iframe 文档')
        const before = hook.snapshot()
        const settingsLink = await waitFor(() => iframe.contentDocument?.querySelector('[data-testid="open-settings"]') as HTMLElement | null)
        settingsLink.click()
        await waitFor(() => iframe.contentDocument?.querySelector('[data-testid="settings-overlay"]'))
        if (!iframe.contentDocument.querySelector('[data-testid="chat-page"]')) throw new Error('打开设置后 ChatPage 被卸载')
        const during = hook.snapshot()
        if (during.messageCount !== before.messageCount) throw new Error('打开设置后消息数量变化')
        return '聊天工作区仍保持挂载'
      })

      await execute('返回聊天后缓存恢复', async () => {
        if (!hook) throw new Error('应用测试钩子不可用')
        const iframe = iframeRef.current
        if (!iframe?.contentDocument) throw new Error('无法读取应用 iframe 文档')
        const close = await waitFor(() => iframe.contentDocument?.querySelector('[data-testid="close-settings"]') as HTMLElement | null)
        close.click()
        await waitFor(() => iframe.contentDocument && !iframe.contentDocument.querySelector('[data-testid="settings-overlay"]'))
        const snapshot = hook.snapshot()
        if (snapshot.currentSessionId !== sessionId) throw new Error('返回后当前会话改变')
        if (snapshot.draft !== draftValue) throw new Error('返回后草稿丢失')
        if (snapshot.scrollPosition !== scrollValue) throw new Error('返回后滚动位置丢失')
        const textarea = iframe.contentDocument.querySelector('[data-testid="chat-composer"]') as HTMLTextAreaElement | null
        if (!textarea || textarea.value !== draftValue) throw new Error('返回后输入框草稿不可见')
        if (snapshot.loadingMessages) throw new Error('返回后仍在加载消息')
        if (snapshot.messageLoadError) throw new Error(snapshot.messageLoadError)
        return `${snapshot.messageCount} 条消息保持可用`
      })

      await execute('实际回复动态数据组件', () => {
        const iframe = iframeRef.current
        if (!iframe?.contentDocument) throw new Error('无法读取应用 iframe 文档')
        const meta = iframe.contentDocument.querySelectorAll('[data-testid="runtime-message-meta"]')
        if (meta.length < 1) throw new Error('未找到回复下方的动态数据组件')
        return `${meta.length} 个运行时组件`
      })

      await execute('多角色说话颜色稳定区分', () => {
        const nodes = speakerProbeRef.current?.querySelectorAll<HTMLElement>('[data-speaker]')
        if (!nodes || nodes.length < 2) throw new Error('说话人组件没有渲染')
        const first = nodes[0].dataset.speakerColor
        const second = nodes[1].dataset.speakerColor
        if (!first || !second) throw new Error('说话人颜色缺失')
        if (first === second) throw new Error('不同角色使用了相同颜色')
        return `${nodes[0].dataset.speaker}=${first}, ${nodes[1].dataset.speaker}=${second}`
      })

      await execute('未知动态变量自动渲染', async () => {
        const container = dataProbeRef.current
        if (!container) throw new Error('动态数据探针未渲染')
        let text = container.textContent || ''
        const groupButton = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes('阵营声望')) as HTMLButtonElement | undefined
        if (!text.includes('学院') && groupButton && groupButton.getAttribute('aria-expanded') !== 'true') {
          groupButton.click()
          await sleep(50)
          text = container.textContent || ''
        }
        for (const expected of ['理智', '72', '阵营声望', '学院', '25']) {
          if (!text.includes(expected)) throw new Error(`动态数据面板缺少：${expected}`)
        }
        return '嵌套未知字段已显示'
      })

      const failed = collected.some((item) => item.status === 'failed')
      const report = {
        status: failed ? 'failed' : 'passed',
        finished_at: new Date().toISOString(),
        user_agent: navigator.userAgent,
        viewport: { width: window.innerWidth, height: window.innerHeight, device_pixel_ratio: window.devicePixelRatio },
        tests: collected,
      }
      try {
        if (runId) await submitSelfTestFrontend(runId, report)
      } catch (error) {
        collected.push({
          name: '上传前端自检结果',
          status: 'failed',
          duration_ms: 0,
          error: error instanceof Error ? error.message : String(error),
        })
      }
      if (!cancelled) {
        setResults([...collected])
        setOverall(collected.some((item) => item.status === 'failed') ? 'failed' : 'passed')
        setFinished(true)
      }
    }

    void run()
    return () => { cancelled = true }
  }, [characterId, runId, sessionId])

  return (
    <div className="min-h-screen bg-tavern-bg-deepest text-tavern-text-primary p-5 sm:p-8">
      <div className="max-w-4xl mx-auto space-y-5">
        <header className="card-parchment">
          <h1 className="text-xl font-semibold">AI Tavern 一键自检</h1>
          <p className="text-sm text-tavern-text-muted mt-2">请保持此页面打开。测试会自动完成并把结果发送回本地诊断服务。</p>
          <div className="mt-4 flex items-center gap-3">
            <span className={`tag ${overall === 'passed' ? 'tag-gold' : ''}`}>{finished ? (overall === 'passed' ? '全部通过' : '发现问题') : '正在测试'}</span>
            <span className="text-xs text-tavern-text-muted">{results.length} 项已完成</span>
          </div>
        </header>

        <section className="card-parchment space-y-2">
          {results.map((result) => (
            <div key={result.name} className="flex items-start gap-3 border-b border-tavern-border-subtle/40 py-3 last:border-0">
              <span className={result.status === 'passed' ? 'text-emerald-400' : 'text-tavern-rose-400'}>{result.status === 'passed' ? '✓' : '✕'}</span>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between gap-3"><strong className="text-sm">{result.name}</strong><small className="text-tavern-text-muted">{result.duration_ms}ms</small></div>
                {result.detail ? <p className="text-xs text-tavern-text-secondary mt-1">{result.detail}</p> : null}
                {result.error ? <p className="text-xs text-tavern-rose-400 mt-1 break-words">{result.error}</p> : null}
              </div>
            </div>
          ))}
          {!results.length ? <p className="text-sm text-tavern-text-muted">正在初始化浏览器测试…</p> : null}
        </section>

        <div className="grid lg:grid-cols-2 gap-4">
          <section className="card-parchment">
            <h2 className="text-sm font-semibold mb-3">说话人颜色探针</h2>
            <div ref={speakerProbeRef}><StructuredMessage message={syntheticMessage}/></div>
          </section>
          <div ref={dataProbeRef}>
            <GenericDataPanel title="动态变量探针" value={{ 理智: 72, 阵营声望: { 学院: 25, 王国: -3 }, 状态: ['警觉', '探索中'] }}/>
          </div>
        </div>

        <iframe
          ref={iframeRef}
          title="AI Tavern application self-test"
          src="/chat?selftest=1"
          className="w-full h-[720px] rounded-xl border border-tavern-border-subtle bg-black"
        />
      </div>
    </div>
  )
}
