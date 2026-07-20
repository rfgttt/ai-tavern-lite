import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import type { Message, MessageSegment, RuntimeState, StatusPanelArtifact } from '@/types'
import InlineCardState from './InlineCardState'
import TextStatusPanel from './TextStatusPanel'

const colorForSpeaker = (name: string) => {
  let hash = 0
  for (let index = 0; index < name.length; index += 1) hash = (hash * 31 + name.charCodeAt(index)) >>> 0
  const hue = hash % 360
  return `hsl(${hue} 68% 70%)`
}

const parseFallback = (content: string): MessageSegment[] => {
  const blocks = content.split(/\n\s*\n/).map((item) => item.trim()).filter(Boolean)
  return blocks.map((block) => {
    const dialogue = block.match(/^(?:【([^】]{1,40})】|([^：:\n]{1,40}))\s*[：:]\s*[“"「](.*)[”"」]$/s)
    if (dialogue) return { type: 'dialogue', speaker: (dialogue[1] || dialogue[2]).trim(), text: dialogue[3].trim() }
    if (block.startsWith('**') && block.endsWith('**')) return { type: 'thought', text: block.slice(2, -2).trim() }
    if (block.startsWith('*') && block.endsWith('*')) return { type: 'narration', text: block.slice(1, -1).trim() }
    return { type: 'markdown', text: block }
  })
}

export default function StructuredMessage({ message, state }: { message: Message; state?: RuntimeState }) {
  if (message.role !== 'assistant') {
    return <div className="markdown-content text-sm leading-relaxed"><ReactMarkdown rehypePlugins={[rehypeSanitize]}>{message.content}</ReactMarkdown></div>
  }

  const segments = message.segments?.length ? message.segments : parseFallback(message.content)
  const speakerMeta = message.speaker_metadata || {}
  const artifacts = message.artifacts || []
  const referencedArtifacts = new Set(segments.filter((segment) => segment.type === 'status-panel-placeholder').map((segment) => segment.artifact_index))

  return (
    <div data-testid="structured-message" className="structured-message">
      {segments.map((segment, index) => {
        if (segment.type === 'dialogue') {
          const color = speakerMeta[segment.speaker]?.color || colorForSpeaker(segment.speaker)
          return (
            <section key={`${segment.speaker}-${index}`} data-speaker={segment.speaker} data-speaker-color={color} className="structured-dialogue" style={{ '--speaker-color': color } as React.CSSProperties}>
              <div className="structured-dialogue__speaker">{segment.speaker}{segment.emotion ? <small> · {segment.emotion}</small> : null}</div>
              <div className="structured-dialogue__text">“{segment.text}”</div>
            </section>
          )
        }
        if (segment.type === 'narration') return <p key={index} className="structured-narration">{segment.text}</p>
        if (segment.type === 'thought') return <p key={index} className="structured-thought">{segment.text}</p>
        if (segment.type === 'action') return <p key={index} className="structured-action">{segment.speaker ? <strong>{segment.speaker}</strong> : null}{segment.text}</p>
        if (segment.type === 'card-state-placeholder') return <InlineCardState key={index} state={state}/>
        if (segment.type === 'status-panel-placeholder') {
          const artifact = artifacts[segment.artifact_index]
          if (artifact?.type === 'status-panel' && artifact.data && typeof artifact.data === 'object') {
            return <TextStatusPanel key={index} panel={artifact.data as StatusPanelArtifact}/>
          }
          return null
        }
        return <div key={index} className="markdown-content text-sm leading-relaxed"><ReactMarkdown rehypePlugins={[rehypeSanitize]}>{segment.text}</ReactMarkdown></div>
      })}
      {artifacts.map((artifact, index) => {
        if (referencedArtifacts.has(index) || artifact.type !== 'status-panel' || !artifact.data || typeof artifact.data !== 'object') return null
        return <TextStatusPanel key={`status-artifact-${index}`} panel={artifact.data as StatusPanelArtifact}/>
      })}
    </div>
  )
}
