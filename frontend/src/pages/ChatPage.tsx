import Sidebar from '@/components/Sidebar'
import ChatView from '@/components/ChatView'
import CharacterPanel from '@/components/CharacterPanel'

export default function ChatPage() {
  return (
    <div data-testid="chat-page" className="flex h-screen overflow-hidden bg-tavern-bg-deepest">
      <Sidebar />
      <ChatView />
      <CharacterPanel />
    </div>
  )
}
