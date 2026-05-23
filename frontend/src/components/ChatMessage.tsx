import type { Message } from '../types/api';
import { CitationsPanel } from './CitationsPanel';

interface Props {
  message: Message;
  formatTime: (d: Date) => string;
}

export function ChatMessage({ message, formatTime }: Props) {
  const isUser = message.role === 'user';

  return (
    <div className={`message-row ${message.role}`} id={`msg-${message.id}`}>
      {/* Avatar */}
      <div className={`avatar ${message.role}`} aria-hidden="true">
        {isUser ? '👤' : '🏦'}
      </div>

      {/* Content */}
      <div className="message-content">
        <div className={`message-bubble${message.blocked ? ' blocked' : ''}`}>
          {message.loading ? (
            <div className="loading-dots" role="status" aria-label="جارٍ التفكير">
              <span /><span /><span />
            </div>
          ) : (
            <span
              dangerouslySetInnerHTML={{ __html: message.content.replace(/\n/g, '<br/>') }}
            />
          )}
        </div>

        {/* Latency */}
        {!isUser && message.latency_ms !== undefined && !message.loading && (
          <div className="latency-badge">
            <span>⚡</span>
            <span>{(message.latency_ms / 1000).toFixed(1)} ثانية</span>
          </div>
        )}

        {/* Timestamp */}
        <div className="message-time" aria-label="وقت الرسالة">
          {formatTime(message.timestamp)}
        </div>

        {/* Citations */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <CitationsPanel sources={message.sources} />
        )}
      </div>
    </div>
  );
}
