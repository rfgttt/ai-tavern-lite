import { useState, useEffect } from 'react'
import { useAppStore } from '@/stores/appStore'
import { testConnection } from '@/api'
import DiagnosticsPanel from '@/components/DiagnosticsPanel'
import type { ConnectionTestResult } from '@/types'
import { Settings as SettingsIcon, User, Cpu, Sliders, Brain, Check, AlertCircle, Trash2, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

interface SectionCardProps {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
}

function SectionCard({ title, icon, children }: SectionCardProps) {
  return (
    <section className="card-parchment mb-5">
      <div className="flex items-center gap-2.5 mb-4 pb-3 border-b border-tavern-border-subtle/50">
        <span className="text-tavern-gold-400">{icon}</span>
        <h2 className="text-sm font-semibold text-tavern-text-primary">{title}</h2>
      </div>
      <div className="space-y-4">
        {children}
      </div>
    </section>
  )
}

interface FormFieldProps {
  label: string
  hint?: string
  children: React.ReactNode
}

function FormField({ label, hint, children }: FormFieldProps) {
  return (
    <div>
      <label className="block text-xs text-tavern-text-secondary mb-1.5 font-medium">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-tavern-text-muted mt-1.5">{hint}</p>}
    </div>
  )
}

export default function SettingsPage({ embedded = false }: { embedded?: boolean }) {
  const settings = useAppStore((state) => state.settings)
  const fetchSettings = useAppStore((state) => state.fetchSettings)
  const updateSettings = useAppStore((state) => state.updateSettings)
  const navigate = useNavigate()

  const [formData, setFormData] = useState({
    provider_name: '',
    base_url: '',
    api_key: '',
    model: '',
    temperature: 0.7,
    top_p: 0.9,
    max_tokens: 1024,
    context_window: 8192,
    username: '用户',
    mock_llm: true,
    auto_memory_extraction: false,
  })

  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null)
  const [testing, setTesting] = useState(false)
  const [saved, setSaved] = useState(false)
  const settingsLocked = settings?.settings_writable === false

  useEffect(() => {
    fetchSettings()
  }, [])

  useEffect(() => {
    if (settings) {
      setFormData({
        provider_name: settings.provider_name,
        base_url: settings.base_url,
        api_key: '',
        model: settings.model,
        temperature: settings.temperature,
        top_p: settings.top_p,
        max_tokens: settings.max_tokens,
        context_window: settings.context_window,
        username: settings.username,
        mock_llm: settings.mock_llm,
        auto_memory_extraction: settings.auto_memory_extraction,
      })
    }
  }, [settings])

  const handleChange = (field: string, value: any) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  const handleSave = async () => {
    if (settingsLocked) return
    try {
      const updateData: any = { ...formData }
      if (!formData.api_key) {
        delete updateData.api_key
      }
      await updateSettings(updateData)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      alert('保存失败')
    }
  }

  const handleClearApiKey = async () => {
    if (settingsLocked) return
    if (!window.confirm('确定要清除已保存的 API Key 吗？')) return
    try {
      await updateSettings({ clear_api_key: true })
      setFormData((previous) => ({ ...previous, api_key: '' }))
      setTestResult({ success: true, message: 'API Key 已清除' })
    } catch {
      setTestResult({ success: false, message: '清除 API Key 失败' })
    }
  }

  const handleTestConnection = async () => {
    if (settingsLocked) return
    setTesting(true)
    setTestResult(null)
    try {
      const updateData: any = { ...formData }
      if (!formData.api_key) {
        delete updateData.api_key
      }
      const res = await testConnection(updateData)
      setTestResult(res.data)
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err?.response?.data?.detail || err.message || '测试失败',
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className={`h-full bg-tavern-bg-deepest tavern-bg ${embedded ? 'rounded-2xl' : ''}`}>
      <div className="h-full overflow-y-auto scrollbar-thin">
        <div className="max-w-2xl mx-auto px-6 py-8">
          {embedded ? <button data-testid="close-settings" onClick={() => navigate('/chat')} className="fixed sm:absolute top-4 right-4 btn-icon z-10" title="返回对话"><X size={18}/></button> : null}
          {/* Page header */}
          <div className="flex items-center gap-3 mb-7">
            <div className="w-10 h-10 rounded-xl bg-tavern-gold-900/30 border border-tavern-border-gold/30 flex items-center justify-center">
              <SettingsIcon size={20} className="text-tavern-gold-400" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-tavern-text-primary">设置</h1>
              <p className="text-xs text-tavern-text-muted">配置模型服务与对话参数</p>
            </div>
          </div>

          {settingsLocked && (
            <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-amber-700/30 bg-amber-900/15 p-3.5 text-sm text-amber-200">
              <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-medium">服务器已锁定网页设置</p>
                <p className="mt-1 text-xs text-amber-200/70">模型地址、密钥和生成参数由服务器环境变量管理，网页端仅供查看。</p>
              </div>
            </div>
          )}

          <fieldset disabled={settingsLocked} className={settingsLocked ? 'opacity-70' : ''}>
          {/* User Settings */}
          <SectionCard title="用户设置" icon={<User size={16} />}>
            <FormField label="用户名称" hint="用于替换角色卡中的 {{user}} 模板变量">
              <input
                type="text"
                value={formData.username}
                onChange={(e) => handleChange('username', e.target.value)}
                className="input"
                placeholder="用户"
              />
            </FormField>
          </SectionCard>

          {/* Model Settings */}
          <SectionCard title="模型服务" icon={<Cpu size={16} />}>
            <div className="flex items-center gap-3 p-3 rounded-lg bg-tavern-bg-tertiary/30 border border-tavern-border-subtle">
              <input
                type="checkbox"
                id="mock_llm"
                checked={formData.mock_llm}
                onChange={(e) => handleChange('mock_llm', e.target.checked)}
                className="w-4 h-4 accent-tavern-gold-500"
              />
              <div>
                <label htmlFor="mock_llm" className="text-sm text-tavern-text-primary cursor-pointer">
                  使用 Mock 模式
                </label>
                <p className="text-[11px] text-tavern-text-muted">无需 API Key，用于功能测试</p>
              </div>
            </div>

            {!formData.mock_llm && (
              <div className="space-y-4 pt-1">
                <FormField label="服务商名称">
                  <input
                    type="text"
                    value={formData.provider_name}
                    onChange={(e) => handleChange('provider_name', e.target.value)}
                    className="input"
                    placeholder="OpenAI Compatible"
                  />
                </FormField>

                <FormField label="Base URL" hint="OpenAI 兼容接口地址，末尾有无 /v1 均可">
                  <input
                    type="text"
                    value={formData.base_url}
                    onChange={(e) => handleChange('base_url', e.target.value)}
                    className="input font-mono text-xs"
                    placeholder="https://api.example.com/v1"
                  />
                </FormField>

                <FormField label="API Key">
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={formData.api_key}
                      onChange={(e) => handleChange('api_key', e.target.value)}
                      className="input font-mono text-xs flex-1"
                      placeholder={settings?.api_key_configured ? '（已配置，留空表示不修改）' : 'sk-...'}
                    />
                    {settings?.api_key_configured && (
                      <button
                        type="button"
                        onClick={handleClearApiKey}
                        className="btn btn-secondary px-3 text-tavern-rose-400"
                        title="清除已保存的 API Key"
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                  {settings?.api_key_configured && settings.api_key_masked && (
                    <p className="text-[11px] text-tavern-text-muted mt-1.5">
                      当前密钥：{settings.api_key_masked}
                    </p>
                  )}
                </FormField>

                <FormField label="Model ID" hint="请填写服务商提供的实际模型名称">
                  <input
                    type="text"
                    value={formData.model}
                    onChange={(e) => handleChange('model', e.target.value)}
                    className="input"
                    placeholder="例如：deepseek-chat"
                  />
                </FormField>
              </div>
            )}
          </SectionCard>

          {/* Generation Parameters */}
          <SectionCard title="生成参数" icon={<Sliders size={16} />}>
            <div className="grid grid-cols-2 gap-4">
              <FormField label={`Temperature: ${formData.temperature}`}>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={formData.temperature}
                  onChange={(e) => handleChange('temperature', parseFloat(e.target.value))}
                  className="w-full accent-tavern-gold-500"
                />
              </FormField>

              <FormField label={`Top P: ${formData.top_p}`}>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={formData.top_p}
                  onChange={(e) => handleChange('top_p', parseFloat(e.target.value))}
                  className="w-full accent-tavern-gold-500"
                />
              </FormField>

              <FormField label="Max Tokens">
                <input
                  type="number"
                  value={formData.max_tokens}
                  onChange={(e) => handleChange('max_tokens', parseInt(e.target.value) || 1024)}
                  className="input"
                />
              </FormField>

              <FormField label="上下文长度">
                <input
                  type="number"
                  value={formData.context_window}
                  onChange={(e) => handleChange('context_window', parseInt(e.target.value) || 8192)}
                  className="input"
                />
              </FormField>
            </div>
          </SectionCard>

          {/* Memory Settings */}
          <SectionCard title="记忆设置" icon={<Brain size={16} />}>
            <div className="flex items-center gap-3 p-3 rounded-lg bg-tavern-bg-tertiary/30 border border-tavern-border-subtle">
              <input
                type="checkbox"
                id="auto_memory"
                checked={formData.auto_memory_extraction}
                onChange={(e) => handleChange('auto_memory_extraction', e.target.checked)}
                className="w-4 h-4 accent-tavern-gold-500"
              />
              <div>
                <label htmlFor="auto_memory" className="text-sm text-tavern-text-primary cursor-pointer">
                  自动提取记忆
                </label>
                <p className="text-[11px] text-tavern-text-muted">实验性功能：从对话中自动提取有价值的信息</p>
              </div>
            </div>
          </SectionCard>
          </fieldset>

          {settings?.diagnostics_enabled && <DiagnosticsPanel />}

          {/* Actions */}
          {!settingsLocked && (
            <div className="flex items-center gap-3 mt-6">
              <button onClick={handleSave} className="btn btn-primary">
                {saved ? (
                  <><Check size={15} /> 已保存</>
                ) : (
                  '保存设置'
                )}
              </button>

              {!formData.mock_llm && (
                <button
                  onClick={handleTestConnection}
                  disabled={testing}
                  className="btn btn-secondary"
                >
                  {testing ? '测试中...' : '测试连接'}
                </button>
              )}
            </div>
          )}

          {/* Test Result */}
          {testResult && (
            <div
              className={`mt-4 p-3.5 rounded-xl text-sm flex items-start gap-2.5 ${
                testResult.success
                  ? 'bg-emerald-900/20 border border-emerald-700/30 text-emerald-300'
                  : 'bg-tavern-rose-600/15 border border-tavern-rose-600/30 text-tavern-rose-400'
              }`}
            >
              {testResult.success ? (
                <Check size={16} className="flex-shrink-0 mt-0.5" />
              ) : (
                <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
              )}
              <span>{testResult.message}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
