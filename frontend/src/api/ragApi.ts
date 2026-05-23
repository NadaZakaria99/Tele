/// <reference types="vite/client" />
import type { ChatRequest, ChatResponse } from '../types/api';

// In Docker: requests go to Nginx proxy via /api prefix
const RAG_BASE = '/api';

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const url = `${RAG_BASE}/v1/chat`;

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`RAG Service error ${res.status}: ${text}`);
  }

  return res.json() as Promise<ChatResponse>;
}

export async function healthCheck(): Promise<boolean> {
  try {
    const url = `${RAG_BASE}/health`;
    const res = await fetch(url, { method: 'GET' });
    return res.ok;
  } catch {
    return false;
  }
}
