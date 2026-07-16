import { useEffect, useState } from 'react'
import { Plus, Trash2, UserRound, X } from 'lucide-react'
import { createPersona, deletePersona, getPersonas } from '@/api'
import type { Persona } from '@/types'

export default function PersonaManager({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [items, setItems] = useState<Persona[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const reload = async () => setItems((await getPersonas()).data)
  useEffect(() => { if (open) void reload() }, [open])
  if (!open) return null

  const add = async () => {
    if (!name.trim()) return
    await createPersona({ name: name.trim(), description, pronouns: '', metadata: {}, is_default: items.length === 0 })
    setName(''); setDescription(''); await reload()
  }

  return <div className="manager-scrim"><section className="manager-modal">
    <header><div><UserRound size={18}/><span>Persona</span></div><button onClick={onClose}><X size={18}/></button></header>
    <div className="manager-body">
      <p className="runtime-note">Persona 是玩家在角色世界中的身份。2.0 Preview 已提供持久化管理，后续可绑定到具体会话。</p>
      <div className="manager-form"><input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="Persona 名称"/><textarea className="textarea" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="外貌、背景、说话方式…"/><button className="btn btn-primary" onClick={() => void add()}><Plus size={14}/>添加</button></div>
      <div className="manager-list">{items.map((item) => <article key={item.id}><div><strong>{item.name}</strong>{item.is_default ? <span className="tag tag-gold">默认</span> : null}<p>{item.description || '未填写描述'}</p></div><button onClick={async () => { await deletePersona(item.id); await reload() }}><Trash2 size={14}/></button></article>)}</div>
    </div>
  </section></div>
}
