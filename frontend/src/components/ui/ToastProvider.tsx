import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'

type ToastKind = 'success' | 'error' | 'info'

interface ToastAction {
  label: string
  onClick: () => void
}

interface ToastItem {
  id: number
  message: string
  kind: ToastKind
  action?: ToastAction
}

interface ToastContextValue {
  showToast: (message: string, kind?: ToastKind, action?: ToastAction) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id))
  }, [])

  const showToast = useCallback((message: string, kind: ToastKind = 'info', action?: ToastAction) => {
    const id = Date.now() + Math.floor(Math.random() * 1000)
    setItems((current) => [...current, { id, message, kind, action }].slice(-4))
    window.setTimeout(() => dismiss(id), action ? 7000 : 4200)
  }, [dismiss])

  const value = useMemo(() => ({ showToast }), [showToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="false">
        {items.map((item) => {
          const Icon = item.kind === 'success' ? CheckCircle2 : item.kind === 'error' ? AlertCircle : Info
          return (
            <div key={item.id} className={`toast toast--${item.kind}`} role={item.kind === 'error' ? 'alert' : 'status'}>
              <Icon size={17} />
              <span>{item.message}</span>
              {item.action ? (
                <button
                  type="button"
                  className="toast__action"
                  onClick={() => {
                    dismiss(item.id)
                    item.action?.onClick()
                  }}
                >
                  {item.action.label}
                </button>
              ) : null}
              <button type="button" aria-label="关闭提示" onClick={() => dismiss(item.id)}><X size={15} /></button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast must be used within ToastProvider')
  return value
}
