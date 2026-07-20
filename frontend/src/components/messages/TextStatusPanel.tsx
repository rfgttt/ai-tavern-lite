import { Clapperboard, CloudSun, MessageCircleHeart, ShieldCheck, UsersRound } from 'lucide-react'
import type { StatusPanelArtifact, StatusPanelSection } from '@/types'

const SectionIcon = ({ kind }: { kind: StatusPanelSection['kind'] }) => {
  if (kind === 'environment') return <CloudSun size={14}/>
  if (kind === 'characters') return <UsersRound size={14}/>
  if (kind === 'interaction') return <MessageCircleHeart size={14}/>
  if (kind === 'atmosphere') return <Clapperboard size={14}/>
  return <ShieldCheck size={14}/>
}

const Fields = ({ fields = [] }: { fields?: StatusPanelSection['fields'] }) => {
  if (!fields?.length) return null
  return (
    <dl className="text-status-fields">
      {fields.map((field, index) => (
        <div key={`${field.label}-${index}`}>
          <dt>{field.icon ? <span>{field.icon}</span> : null}{field.label}</dt>
          <dd>{field.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export default function TextStatusPanel({ panel }: { panel: StatusPanelArtifact }) {
  return (
    <section data-testid="text-status-panel" className="text-status-panel">
      <header>
        <span><ShieldCheck size={16}/></span>
        <div>
          <strong>{panel.title || '剧情状态'}</strong>
          <small>原生安全解析 · 不执行角色卡脚本</small>
        </div>
      </header>

      <div className="text-status-sections">
        {panel.sections.map((section, sectionIndex) => (
          <section className={`text-status-section text-status-section--${section.kind}`} key={`${section.title}-${sectionIndex}`}>
            <h4><SectionIcon kind={section.kind}/><span>{section.title}</span></h4>
            <Fields fields={section.fields}/>
            {section.characters?.length ? (
              <div className="text-status-characters">
                {section.characters.map((character, characterIndex) => (
                  <article key={`${character.name}-${characterIndex}`}>
                    <h5><span>{character.badge || '✦'}</span>{character.name}</h5>
                    <Fields fields={character.fields}/>
                  </article>
                ))}
              </div>
            ) : null}
            {section.text ? <p className="text-status-prose">{section.text}</p> : null}
          </section>
        ))}
      </div>

      {panel.warnings?.length ? (
        <footer>{panel.warnings.map((warning) => <span key={warning}>{warning}</span>)}</footer>
      ) : null}
    </section>
  )
}
