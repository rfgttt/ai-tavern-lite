import { waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { streamChat } from '@/api'

const encodeFrames = (frames: string[]) => {
  const encoder = new TextEncoder()
  return new ReadableStream<Uint8Array>({
    start(controller) {
      frames.forEach((frame) => controller.enqueue(encoder.encode(frame)))
      controller.close()
    },
  })
}

describe('streamChat', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('dispatches SSE message, content and done events in order', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        encodeFrames([
          'data: {"type":"message","user_message":null,"assistant_message":{"id":"assistant-1"}}\n\n',
          'data: {"type":"content","content":"你","message_id":"assistant-1"}\n\n',
          'data: {"type":"content","content":"好","message_id":"assistant-1"}\n\n',
          'data: {"type":"done","message_id":"assistant-1","status":"complete","content":"你好","runtime":null,"state":{},"revision":1}\n\n',
        ]),
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const onMessage = vi.fn()
    const onChunk = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    const controller = streamChat('session-1', '你好', {
      onRuntime: vi.fn(),
      onMessage,
      onChunk,
      onDone,
      onError,
    })

    expect(controller).toBeInstanceOf(AbortController)

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1))

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat/stream',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ session_id: 'session-1', message: '你好' }),
      }),
    )
    expect(onMessage).toHaveBeenCalledTimes(1)
    expect(onChunk.mock.calls.map(([content]) => content)).toEqual(['你', '好'])
    expect(onError).not.toHaveBeenCalled()
  })

  it('reports an unexpected stream end when no done event arrives', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          encodeFrames(['data: {"type":"content","content":"部分回复","message_id":"assistant-1"}\n\n']),
          { status: 200 },
        ),
      ),
    )

    const onError = vi.fn()
    streamChat('session-1', '继续', {
      onRuntime: vi.fn(),
      onMessage: vi.fn(),
      onChunk: vi.fn(),
      onDone: vi.fn(),
      onError,
    })

    await waitFor(() => expect(onError).toHaveBeenCalledWith('数据流意外结束'))
  })
})
