import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import CharacterSecurityDialog from '@/components/CharacterSecurityDialog'
import { characterSecurityScanFixture } from '../mocks/fixtures'
import { renderWithRouter } from '../testUtils'

describe('CharacterSecurityDialog', () => {
  it('explains blocked code and disables original import', async () => {
    const user = userEvent.setup()
    const onSafeCopy = vi.fn()
    renderWithRouter(
      <CharacterSecurityDialog
        open
        scan={characterSecurityScanFixture}
        onCancel={vi.fn()}
        onSafeCopy={onSafeCopy}
        onQuarantine={vi.fn()}
        onOriginal={vi.fn()}
      />,
    )

    expect(screen.getByRole('dialog', { name: '角色卡安全检查' })).toHaveTextContent('检测到 AI 提示词注入')
    expect(screen.getByText('evil.example')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '原样导入' })).toBeDisabled()
    expect(screen.getByText(/不会访问角色卡中的网址/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '安全导入（推荐）' }))
    expect(onSafeCopy).toHaveBeenCalledOnce()
  })



  it('disables all storage actions when the card structure exceeds limits', () => {
    const scan = {
      ...characterSecurityScanFixture,
      report: {
        ...characterSecurityScanFixture.report,
        can_import_original: false,
        can_import_safe: false,
      },
    }
    renderWithRouter(
      <CharacterSecurityDialog
        open
        scan={scan}
        onCancel={vi.fn()}
        onSafeCopy={vi.fn()}
        onQuarantine={vi.fn()}
        onOriginal={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: '隔离保存' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '原样导入' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '安全导入（推荐）' })).toBeDisabled()
  })

  it('offers only safe-copy remediation for an existing character', () => {
    renderWithRouter(
      <CharacterSecurityDialog
        open
        scan={characterSecurityScanFixture}
        existingCharacter
        onCancel={vi.fn()}
        onSafeCopy={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: '生成安全副本' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '隔离保存' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '原样导入' })).not.toBeInTheDocument()
  })
})
