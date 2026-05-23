import { useState } from 'react';
import type { UserRole } from './api';
import LoginScreen from './LoginScreen';
import ChatScreen from './ChatScreen';
import './index.css';

export default function App() {
  const [session, setSession] = useState<{ role: UserRole; name: string } | null>(null);

  if (!session) {
    return (
      <LoginScreen
        onLogin={(role, name) => setSession({ role, name })}
      />
    );
  }

  return (
    <ChatScreen
      userRole={session.role}
      userName={session.name}
      onLogout={() => setSession(null)}
    />
  );
}
