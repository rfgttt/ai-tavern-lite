import { useEffect, useState } from 'react'
import { GitBranch, RotateCcw, Save, Trash2, X } from 'lucide-react'
import { deleteBranch, getBranches, restoreBranch, saveBranch } from '@/api'
import { useAppStore } from '@/stores/appStore'
import type { SessionBranch } from '@/types'

export default function BranchManager({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { currentSession, refreshCurrentSession } = useAppStore()
  const [branches, setBranches] = useState<SessionBranch[]>([])
  const [title, setTitle] = useState('当前剧情存档')
  const reload = async () => {
    if (!currentSession) return setBranches([])
    setBranches((await getBranches(currentSession.id)).data)
  }
  useEffect(() => { if (open) void reload() }, [open, currentSession?.id])
  if (!open) return null

  return <div className="manager-scrim"><section className="manager-modal">
    <header><div><GitBranch size={18}/><span>剧情分支</span></div><button onClick={onClose}><X size={18}/></button></header>
    <div className="manager-body">
      {!currentSession ? <p className="runtime-empty">先选择一个会话。</p> : <>
        <div className="manager-form manager-form--inline"><input className="input" value={title} onChange={(event) => setTitle(event.target.value)}/><button className="btn btn-primary" onClick={async () => { await saveBranch(currentSession.id, { title: title || '剧情存档' }); await reload() }}><Save size={14}/>保存当前</button></div>
        <div className="manager-list">{branches.map((branch) => <article key={branch.id}><div><strong>{branch.title}</strong><p>{branch.message_count} 条消息 · 状态 r{branch.runtime_revision}</p></div><div className="flex gap-1"><button title="恢复" onClick={async () => { if (!confirm(`恢复到“${branch.title}”？当前未保存内容会被替换。`)) return; await restoreBranch(currentSession.id, branch.id); await refreshCurrentSession(); onClose() }}><RotateCcw size={14}/></button><button title="删除" onClick={async () => { await deleteBranch(currentSession.id, branch.id); await reload() }}><Trash2 size={14}/></button></div></article>)}</div>
      </>}
    </div>
  </section></div>
}
