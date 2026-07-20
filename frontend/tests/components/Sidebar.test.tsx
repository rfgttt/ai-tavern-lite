import { screen, waitFor } from '@testing-library/react'
import { AxiosHeaders, type AxiosResponse } from 'axios'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '@/api'
import Sidebar from '@/components/Sidebar'
import { useAppStore } from '@/stores/appStore'
import { characterSecurityScanFixture, charactersFixture } from '../mocks/fixtures'
import { resetAppStore, renderWithRouter } from '../testUtils'

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api')>()
  return {
    ...actual,
    scanCharacterCard: vi.fn(),
    importCharacter: vi.fn(),
  }
})

const axiosResponse = <T,>(data: T): AxiosResponse<T> => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: new AxiosHeaders(),
  config: { headers: new AxiosHeaders() },
})

describe('Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetAppStore()
    vi.mocked(api.scanCharacterCard).mockResolvedValue(axiosResponse(characterSecurityScanFixture))
    vi.mocked(api.importCharacter).mockImplementation(async (_file, securityMode = 'safe_copy') =>
      axiosResponse({
        ...charactersFixture[0],
        id: `imported-${securityMode}`,
        name: securityMode === 'safe_copy' ? '风险角色卡' : '风险角色卡（隔离）',
      }),
    )
  })

  it('loads characters and lets the user select one', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    const characterButton = await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(characterButton)

    await waitFor(() => {
      expect(useAppStore.getState().selectedCharacter?.name).toBe('林雅')
      expect(useAppStore.getState().sessions).toHaveLength(1)
    })
  })

  it('opens the new-session wizard even when no character was preselected', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(screen.getByTitle('新建对话'))

    expect(screen.getByRole('dialog', { name: '新建会话' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /单角色对话/ })).toHaveClass('is-selected')
  })

  it('blocks a new session when the real model configuration is incomplete', async () => {
    const user = userEvent.setup()
    useAppStore.setState({
      settings: {
        provider_name: 'OpenAI Compatible',
        base_url: 'https://api.example.com/v1',
        model: 'test-model',
        temperature: 0.7,
        top_p: 0.9,
        max_tokens: 1024,
        context_window: 8192,
        username: '用户',
        mock_llm: false,
        auto_memory_extraction: false,
  auto_state_update_recovery: true,
        api_key_configured: false,
        api_key_masked: '',
        api_key_storage: 'windows_dpapi',
        api_key_error: '',
        custom_headers: {},
        settings_writable: true,
        diagnostics_enabled: true,
        selftest_enabled: true,
      },
    })
    renderWithRouter(<Sidebar />)

    await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(screen.getByTitle('新建对话'))
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    await user.click(screen.getByRole('button', { name: /下一步/ }))
    await user.click(await screen.findByRole('button', { name: /创建会话/ }))

    expect(await screen.findByText(/真实模型配置不完整：缺少API Key/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '打开设置' })).toBeInTheDocument()
    expect(useAppStore.getState().currentSession).toBeNull()
  })

  it('opens the built-in character creator', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await user.click(screen.getByTitle('新建角色'))

    expect(screen.getByRole('dialog', { name: '新建角色' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '创建角色' })).toBeDisabled()
  })

  it('opens edit and delete actions from the character menu', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(screen.getByRole('button', { name: '角色菜单 林雅' }))
    await user.click(screen.getByRole('button', { name: /编辑角色/ }))

    expect(screen.getByRole('dialog', { name: /编辑角色：林雅/ })).toBeInTheDocument()
    expect(screen.getByLabelText('角色名称 *')).toHaveValue('林雅')
  })
  it('deletes a character only after explicit confirmation', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(screen.getByRole('button', { name: '角色菜单 林雅' }))
    await user.click(screen.getByRole('button', { name: /删除角色/ }))

    expect(screen.getByRole('dialog', { name: '删除角色' })).toHaveTextContent('相关会话、消息和角色记忆')
    await user.click(screen.getByRole('button', { name: '删除角色' }))

    await waitFor(() => expect(useAppStore.getState().characters.some((item) => item.id === 'character-linya')).toBe(false))
    expect(await screen.findByText('角色“林雅”已删除')).toBeInTheDocument()
  })

  it('exports a character from its action menu', async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:character-export')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

    renderWithRouter(<Sidebar />)
    await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(screen.getByRole('button', { name: '角色菜单 林雅' }))
    await user.click(screen.getByRole('button', { name: /导出角色/ }))

    expect(await screen.findByText('角色“林雅”已导出')).toBeInTheDocument()
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:character-export')
  })

  it('scans a card before import and defaults to a safe copy', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await screen.findByRole('button', { name: /选择角色 林雅/ })
    const file = new File(['{"name":"风险角色卡"}'], 'risk-card.json', { type: 'application/json' })
    await user.upload(screen.getByTestId('character-card-file-input'), file)

    expect(await screen.findByRole('dialog', { name: '角色卡安全检查' }, { timeout: 3000 })).toHaveTextContent('AI 提示词注入')
    expect(api.scanCharacterCard).toHaveBeenCalledWith(file)
    await user.click(screen.getByRole('button', { name: '安全导入（推荐）' }))

    await waitFor(() => expect(useAppStore.getState().selectedCharacter?.id).toBe('imported-safe_copy'))
    expect(await screen.findByText('已安全导入角色“风险角色卡”')).toBeInTheDocument()
    expect(api.importCharacter).toHaveBeenCalledWith(file, 'safe_copy')
  }, 10000)

  it('keeps the current selection when a risky card is saved in quarantine', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    const original = await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(original)
    await waitFor(() => expect(useAppStore.getState().selectedCharacter?.name).toBe('林雅'))

    const file = new File(['{"name":"风险角色卡"}'], 'risk-card.json', { type: 'application/json' })
    await user.upload(screen.getByTestId('character-card-file-input'), file)
    await user.click(await screen.findByRole('button', { name: '隔离保存' }, { timeout: 3000 }))

    expect(await screen.findByText('已隔离保存角色“风险角色卡（隔离）”')).toBeInTheDocument()
    expect(useAppStore.getState().selectedCharacter?.name).toBe('林雅')
    expect(api.scanCharacterCard).toHaveBeenCalledWith(file)
    expect(api.importCharacter).toHaveBeenCalledWith(file, 'quarantine')
  }, 10000)

  it('rescans an existing card and creates a separate safe copy', async () => {
    const user = userEvent.setup()
    renderWithRouter(<Sidebar />)

    await screen.findByRole('button', { name: /选择角色 林雅/ })
    await user.click(screen.getByRole('button', { name: '角色菜单 林雅' }))
    await user.click(screen.getByRole('button', { name: /安全检查/ }))

    expect(await screen.findByRole('button', { name: '生成安全副本' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '生成安全副本' }))

    await waitFor(() => expect(useAppStore.getState().selectedCharacter?.name).toBe('林雅（安全副本）'))
    expect(await screen.findByText('已创建“林雅（安全副本）”')).toBeInTheDocument()
  })

})
