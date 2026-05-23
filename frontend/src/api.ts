// API client for the NBE Knowledge Assistant backend

const API_BASE = '/api';

export type UserRole = 'teller' | 'legal_counsel' | 'manager';

export interface SourceChunk {
  id: number;
  doc_id: string;
  page_num: number;
  content: string;
  crop_url?: string;
  page_image_url?: string;
  block_type?: string;
  cosine_distance?: number;
  reranker_score?: number;
}

export interface ChatResponse {
  answer: string;
  sources: SourceChunk[];
  stages: string[];
  latency_ms: number;
}

export interface HealthStatus {
  status: string;
  milvus: string;
  collection_entities: number;
}

export async function checkHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}

export async function sendQuery(
  query: string,
  role: UserRole
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/v1/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, role }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onStage: (stage: string) => void;
  onSources: (sources: SourceChunk[]) => void;
  onDone: (latency_ms: number) => void;
  onError: (error: Error) => void;
}

export async function sendQueryStream(
  query: string,
  role: UserRole,
  callbacks: StreamCallbacks
) {
  try {
    const res = await fetch(`${API_BASE}/v1/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, role }),
    });

    if (!res.ok || !res.body) {
      throw new Error(`API error ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep the incomplete line in the buffer

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.substring(6);
          try {
            const data = JSON.parse(dataStr);
            if (data.event === 'token') callbacks.onToken(data.text);
            else if (data.event === 'stage') callbacks.onStage(data.stage);
            else if (data.event === 'sources') callbacks.onSources(data.sources);
            else if (data.event === 'done') callbacks.onDone(data.latency_ms);
            else if (data.event === 'error') callbacks.onError(new Error(data.detail));
          } catch (e) {
            console.error('SSE JSON parsing error', e);
          }
        }
      }
    }
  } catch (err) {
    callbacks.onError(err instanceof Error ? err : new Error(String(err)));
  }
}
