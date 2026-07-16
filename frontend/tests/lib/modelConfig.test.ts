import { describe, expect, it } from 'vitest'
import { getModelConfigurationIssue } from '@/lib/modelConfig'
import { appSettingsFixture } from '../mocks/fixtures'

describe('getModelConfigurationIssue', () => {
  it('accepts Mock mode without an API key', () => {
    expect(getModelConfigurationIssue(appSettingsFixture)).toBeNull()
  })

  it('lists every missing real-model field', () => {
    const issue = getModelConfigurationIssue({
      ...appSettingsFixture,
      mock_llm: false,
      base_url: '',
      model: '',
      api_key_configured: false,
    })

    expect(issue?.missing).toEqual(['Base URL', 'API Key', '模型名称'])
    expect(issue?.message).toContain('Base URL、API Key、模型名称')
  })

  it('accepts a complete real-model configuration', () => {
    expect(getModelConfigurationIssue({
      ...appSettingsFixture,
      mock_llm: false,
      api_key_configured: true,
    })).toBeNull()
  })
})
