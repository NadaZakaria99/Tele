import { useState, useCallback, useRef } from 'react';
import type { Message, Role } from '../types/api';
import { sendChat } from '../api/ragApi';

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' });
}

export function useChat(role: Role) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (query: string) => {
    if (!query.trim() || loading) return;

    setError(null);

    const userMsg: Message = {
      id: generateId(),
      role: 'user',
      content: query.trim(),
      timestamp: new Date(),
    };

    const loadingMsg: Message = {
      id: generateId(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      loading: true,
    };

    setMessages(prev => [...prev, userMsg, loadingMsg]);
    setLoading(true);

    try {
      const response = await sendChat({ query: query.trim(), role });

      const assistantMsg: Message = {
        id: loadingMsg.id,
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
        blocked: response.blocked,
        latency_ms: response.latency_ms,
        timestamp: new Date(),
        loading: false,
      };

      setMessages(prev =>
        prev.map(m => m.id === loadingMsg.id ? assistantMsg : m)
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'حدث خطأ غير متوقع. يُرجى المحاولة مرة أخرى.';
      setError(msg);

      setMessages(prev =>
        prev.map(m =>
          m.id === loadingMsg.id
            ? { ...m, content: msg, loading: false, blocked: true }
            : m
        )
      );
    } finally {
      setLoading(false);
    }
  }, [loading, role]);

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setError(null);
  }, []);

  const dismissError = useCallback(() => setError(null), []);

  return {
    messages,
    loading,
    error,
    sendMessage,
    clearMessages,
    dismissError,
    formatTime,
  };
}
