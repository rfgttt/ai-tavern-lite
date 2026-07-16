import type { AppSettings } from '@/types'

export interface ModelConfigurationIssue {
  missing: string[]
  message: string
}

export const getModelConfigurationIssue = (
  settings: AppSettings | null,
): ModelConfigurationIssue | null => {
  if (!settings) {
    return {
      missing: ['模型设置'],
      message: '模型设置尚未加载，请打开设置确认后重试。',
    }
  }

  if (settings.mock_llm) return null

  const missing = [
    !settings.base_url.trim() ? 'Base URL' : '',
    !settings.api_key_configured ? 'API Key' : '',
    !settings.model.trim() ? '模型名称' : '',
  ].filter(Boolean)

  if (missing.length === 0) return null

  return {
    missing,
    message: `真实模型配置不完整：缺少${missing.join('、')}。请完善设置或重新开启 Mock 模式。`,
  }
}
