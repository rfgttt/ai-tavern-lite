import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as backupApi from '@/api'
import SettingsPage from '@/pages/SettingsPage'
import { renderWithRouter, resetAppStore } from '../testUtils'

const currentStatus = {
  format_version: 1,
  current: {
    database_path: 'C:/Users/Test/AppData/Local/AI-Tavern-Lite/data/ai_tavern.db',
    exists: true,
    revision: '20260717_0001',
    counts: { characters: 1, sessions: 1, messages: 1, memories: 0 },
    integrity: 'ok',
  },
  pending_restore: null,
  portable_backup_excludes: ['api_key', 'custom_headers', 'database_instance_id'],
}

const stagedRestore = {
  success: true,
  message: '恢复包已验证并暂存。请停止服务后重新启动，恢复才会生效。',
  restore_id: 'restore-test',
  staged_at: '2026-07-19T01:00:00Z',
  backup_created_at: '2026-07-18T20:00:00Z',
  source_app_version: '2.2.0-preview.1',
  alembic_revision: '20260717_0001',
  counts: { characters: 4, sessions: 11, messages: 74, memories: 0 },
  asset_count: 2,
  restart_required: true,
}

describe('SettingsPage backup and restore', () => {
  beforeEach(() => {
    resetAppStore()
    vi.restoreAllMocks()
  })

  it('shows the current data summary and stages a validated restore for restart', async () => {
    let pending = false
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const statusSpy = vi.spyOn(backupApi, 'getBackupStatus').mockImplementation(async () => ({
      data: {
        ...currentStatus,
        pending_restore: pending ? stagedRestore : null,
      },
    } as never))
    const restoreSpy = vi.spyOn(backupApi, 'prepareBackupRestore').mockImplementation(async () => {
      pending = true
      return { data: stagedRestore } as never
    })

    renderWithRouter(<SettingsPage />, ['/settings'])

    expect(await screen.findByText('完整备份与恢复')).toBeInTheDocument()
    expect(await screen.findByTestId('backup-current-summary')).toHaveTextContent('角色')
    expect(screen.getByTestId('backup-current-summary')).toHaveTextContent('消息')

    const user = userEvent.setup()
    const file = new File(['portable-backup'], 'backup.zip', { type: 'application/zip' })
    const fileInput = screen.getByTestId('restore-backup-file') as HTMLInputElement
    const prepareButton = screen.getByTestId('prepare-full-restore')
    await user.upload(fileInput, file)
    await waitFor(() => expect(prepareButton).toBeEnabled())
    await user.click(prepareButton)

    await waitFor(() => expect(restoreSpy).toHaveBeenCalledWith(file), { timeout: 5000 })
    expect(await screen.findByTestId('pending-restore', {}, { timeout: 5000 })).toHaveTextContent('已有已验证的待恢复任务')
    expect(screen.getByTestId('pending-restore')).toHaveTextContent('角色 4')
    expect(screen.getAllByText(/停止服务并重新启动/).length).toBeGreaterThan(0)
    expect(statusSpy).toHaveBeenCalledTimes(2)
  })
})
