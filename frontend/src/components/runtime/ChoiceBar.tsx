import { Compass, ChevronRight } from 'lucide-react'

export default function ChoiceBar({ choices, disabled, onChoose }: { choices: string[]; disabled?: boolean; onChoose: (choice: string) => void }) {
  if (!choices.length) return null
  return (
    <div className="choice-bar">
      <div className="choice-bar__label"><Compass size={14}/>可选行动</div>
      <div className="choice-bar__list">
        {choices.map((choice, index) => (
          <button key={`${choice}-${index}`} disabled={disabled} onClick={() => onChoose(choice)}>
            <span>{choice}</span><ChevronRight size={14}/>
          </button>
        ))}
      </div>
    </div>
  )
}
