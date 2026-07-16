import { useEffect, useState } from 'react'
import { MessageSquare, Plus, Trash2, Users, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { createGroup, deleteGroup, getGroups } from '@/api'
import { useAppStore } from '@/stores/appStore'
import type { CharacterGroup } from '@/types'

export default function GroupManager({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const { characters, selectCharacter, createSession, selectSession } = useAppStore()
  const [groups, setGroups] = useState<CharacterGroup[]>([])
  const [name, setName] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const reload = async () => setGroups((await getGroups()).data)
  useEffect(() => { if (open) void reload() }, [open])
  if (!open) return null

  const add = async () => {
    if (!name.trim() || !selected.length) return
    await createGroup({ name: name.trim(), character_ids: selected, description: 'AI Tavern 2.0 多角色编组' })
    setName(''); setSelected([]); await reload()
  }

  return <div className="manager-scrim"><section className="manager-modal">
    <header><div><Users size={18}/><span>多角色编组</span></div><button onClick={onClose}><X size={18}/></button></header>
    <div className="manager-body">
      <div className="manager-form"><input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="小队名称"/><div className="manager-check-grid">{characters.map((character) => <label key={character.id}><input type="checkbox" checked={selected.includes(character.id)} onChange={() => setSelected((current) => current.includes(character.id) ? current.filter((id) => id !== character.id) : [...current, character.id])}/><span>{character.name}</span></label>)}</div><button className="btn btn-primary" onClick={() => void add()}><Plus size={14}/>创建编组</button></div>
      <div className="manager-list">{groups.map((group) => <article key={group.id}><div><strong>{group.name}</strong><p>{group.members?.map((item) => item.name).join('、') || `${group.character_ids.length} 名角色`}</p></div><div className="flex gap-1"><button title="开始群聊" onClick={async () => { const primary = characters.find((item) => item.id === group.character_ids[0]); if (!primary) return; selectCharacter(primary); const session = await createSession(primary.id, { title: group.name, group_id: group.id }); await selectSession(session); navigate('/chat'); onClose() }}><MessageSquare size={14}/></button><button onClick={async () => { await deleteGroup(group.id); await reload() }}><Trash2 size={14}/></button></div></article>)}</div>
    </div>
  </section></div>
}
