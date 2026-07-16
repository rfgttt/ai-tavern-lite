import { AlertTriangle, X } from 'lucide-react'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  busy?: boolean
  destructive?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  busy = false,
  destructive = false,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  if (!open) return null

  return (
    <div className="manager-scrim" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onCancel()
    }}>
      <section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
        <header>
          <div><AlertTriangle size={18} /><span id="confirm-dialog-title">{title}</span></div>
          <button type="button" aria-label="关闭" disabled={busy} onClick={onCancel}><X size={18} /></button>
        </header>
        <div className="confirm-dialog__body">
          <p>{description}</p>
          <div className="confirm-dialog__actions">
            <button type="button" className="btn btn-secondary" disabled={busy} onClick={onCancel}>取消</button>
            <button
              type="button"
              className={`btn ${destructive ? 'btn-danger' : 'btn-primary'}`}
              disabled={busy}
              onClick={onConfirm}
            >
              {busy ? '处理中…' : confirmLabel}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
