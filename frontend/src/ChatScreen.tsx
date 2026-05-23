import React, { useState, useEffect, useRef, useCallback } from 'react';
import type { UserRole, SourceChunk } from './api';
import { sendQueryStream } from './api';
import CitationPanel from './CitationPanel';
import styles from './ChatScreen.module.css';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'blocked' | 'error';
  content: string;
  sources?: SourceChunk[];
  stages?: string[];
  latency_ms?: number;
  ts: string;
}

interface ChatScreenProps {
  userRole: UserRole;
  userName: string;
  onLogout: () => void;
}

const ROLE_LABELS: Record<UserRole, { ar: string; en: string; color: string; icon: string }> = {
  teller: { ar: 'موظف خدمة العملاء', en: 'Branch Teller', color: '#4A9EFF', icon: '🏦' },
  legal_counsel: { ar: 'المستشار القانوني', en: 'Senior Legal Counsel', color: '#C9A84C', icon: '⚖️' },
  manager: { ar: 'المدير', en: 'Manager', color: '#3FB950', icon: '👔' },
};

const EXAMPLE_QUERIES: Record<UserRole, string[]> = {
  teller: [
    'ما هي المصطلحات المستخدمة في دليل الاجراءات؟',
    'ما هي العوائد الهامشية وفقاً للتعميمات الأخيرة؟',
    'ما هي اشتراطات البنك المركزي بشأن المخاطر الائتمانية؟',
  ],
  legal_counsel: [
    'ما هي الإجراءات القانونية المتعلقة بالمديونيات المتعثرة؟',
    'ما هي العوائد الهامشية وفقاً للتعميمات الأخيرة؟',
    'ما هي اشتراطات البنك المركزي بشأن المخاطر الائتمانية؟',
  ],
  manager: [
    'ما هي معايير الرقابة الداخلية على العمليات المصرفية؟',
    'ما هي حدود صلاحيات الموافقة على العمليات؟',
    'ما هي متطلبات الإفصاح والشفافية؟',
  ],
};



function SparkleIcon({ animated = false }: { animated?: boolean }) {
  return (
    <div className={animated ? styles.sparkleContainer : ''}>
      <svg viewBox="0 0 24 24" className={`${styles.sparkleIcon} ${!animated ? styles.sparkleStatic : ''}`} fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 1L14.5 8.5L22 11L14.5 13.5L12 21L9.5 13.5L2 11L9.5 8.5L12 1Z" fill="#D98A6C" />
        <path d="M19.5 4.5L18 8L21.5 9.5L19.5 4.5Z" fill="#D98A6C" />
        <path d="M4.5 19.5L6 16L2.5 14.5L4.5 19.5Z" fill="#D98A6C" />
        <path d="M19.5 19.5L16 18L14.5 21.5L19.5 19.5Z" fill="#D98A6C" />
        <path d="M4.5 4.5L8 6L9.5 2.5L4.5 4.5Z" fill="#D98A6C" />
      </svg>
    </div>
  );
}


export default function ChatScreen({ userRole, userName, onLogout }: ChatScreenProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeSources, setActiveSources] = useState<SourceChunk[]>([]);
  const [selectedCitation, setSelectedCitation] = useState<SourceChunk | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const roleInfo = ROLE_LABELS[userRole];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = useCallback(async (query: string) => {
    const q = query.trim();
    if (!q || loading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: q,
      ts: new Date().toLocaleTimeString('ar-EG'),
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    setActiveSources([]);

    const assistantMsgId = (Date.now() + 1).toString();
    const initialAssistantMsg: Message = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      stages: [],
      sources: [],
      ts: new Date().toLocaleTimeString('ar-EG'),
    };
    setMessages(prev => [...prev, initialAssistantMsg]);

    // --- Jitter Buffer Setup for Smooth Typewriter Effect ---
    const tokenBuffer = { current: '' };
    let isStreamDone = false;
    let displayedContent = '';
    let flushInterval: ReturnType<typeof setInterval> | null = null;

    const startFlushing = () => {
      if (flushInterval) return;
      flushInterval = setInterval(() => {
        if (tokenBuffer.current.length > 0) {
          // Dynamic speed: if the buffer grows large, consume characters faster
          const bufferSize = tokenBuffer.current.length;
          const charsToTake = Math.max(1, Math.ceil(bufferSize / 8));

          const chunk = tokenBuffer.current.substring(0, charsToTake);
          tokenBuffer.current = tokenBuffer.current.substring(charsToTake);

          displayedContent += chunk;

          setMessages(prev => prev.map(msg =>
            msg.id === assistantMsgId ? { ...msg, content: displayedContent } : msg
          ));
        } else if (isStreamDone) {
          if (flushInterval) clearInterval(flushInterval);
        }
      }, 30); // Render loop: ~33 fps
    };

    try {
      await sendQueryStream(q, userRole, {
        onToken: (token) => {
          setLoading(false); // Stop typing indicator
          tokenBuffer.current += token;
          startFlushing();
        },
        onStage: (stage) => {
          setMessages(prev => prev.map(msg =>
            msg.id === assistantMsgId ? { ...msg, stages: [...(msg.stages || []), stage] } : msg
          ));
          if (stage.startsWith('safety_blocked') || stage === 'topic_blocked' || stage.startsWith('response_blocked')) {
            setMessages(prev => prev.map(msg =>
              msg.id === assistantMsgId ? { ...msg, role: 'blocked' } : msg
            ));
          }
        },
        onSources: (sources) => {
          setMessages(prev => prev.map(msg =>
            msg.id === assistantMsgId ? { ...msg, sources } : msg
          ));
          if (sources.length > 0) setActiveSources(sources);
          else setActiveSources([]); // Clear active sources if empty
        },
        onDone: (latency_ms) => {
          isStreamDone = true;
          setMessages(prev => prev.map(msg =>
            msg.id === assistantMsgId ? { ...msg, latency_ms } : msg
          ));
          setLoading(false);
          // If buffer was empty, clear interval immediately just in case
          if (tokenBuffer.current.length === 0 && flushInterval) {
            clearInterval(flushInterval);
          }
        },
        onError: (err) => {
          isStreamDone = true;
          setMessages(prev => prev.map(msg =>
            msg.id === assistantMsgId ? { ...msg, role: 'error', content: msg.content || err.message } : msg
          ));
          setLoading(false);
        }
      });
    } catch (err: unknown) {
      isStreamDone = true;
      setMessages(prev => prev.map(msg =>
        msg.id === assistantMsgId ? {
          ...msg,
          role: 'error',
          content: err instanceof Error ? err.message : 'حدث خطأ غير متوقع'
        } : msg
      ));
      setLoading(false);
    }
  }, [loading, userRole]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(input);
    }
  };

  return (
    <div className={styles.shell}>
      {/* ── Sidebar ── */}
      <aside className={styles.sidebar}>
        {/* Logo */}
        <div className={styles.sidebarLogoWrapper}>
          <img
            src="/nbe_logo.png"
            alt="البنك الأهلي المصري"
            className={styles.animatedSidebarLogo}
          />
        </div>

        <div className={styles.sidebarDivider} />

        {/* User profile */}
        <div className={styles.userProfile}>
          <div className={styles.userAvatar} style={{ background: `${roleInfo.color}22`, borderColor: `${roleInfo.color}44` }}>
            {roleInfo.icon}
          </div>
          <div>
            <div className={styles.userName}>{userName}</div>
            <div className={styles.userRole} style={{ color: roleInfo.color }}>{roleInfo.ar}</div>
            <div className={styles.userRoleEn}>{roleInfo.en}</div>
          </div>
        </div>



        {/* Example queries */}
        <div className={styles.sidebarSection}>
          <div className={styles.sidebarSectionTitle}>أسئلة مقترحة</div>
          {EXAMPLE_QUERIES[userRole].map(q => (
            <button key={q} className={styles.exampleBtn} onClick={() => handleSend(q)}>
              {q}
            </button>
          ))}
        </div>

        <div className={styles.sidebarBottom}>
          <button className={styles.clearBtn} onClick={() => { setMessages([]); setActiveSources([]); }}>
            مسح المحادثة
          </button>
          <button className={styles.logoutBtn} onClick={onLogout}>
            تسجيل الخروج
          </button>
        </div>
      </aside>

      {/* ── Main chat area ── */}
      <main className={styles.main}>
        {/* Header */}
        <header className={styles.header}>
          <div>
            <h1 className={styles.headerTitle}>المساعد الذكي للمعرفة المصرفية</h1>
          </div>
          <div className={styles.headerBadge} style={{ borderColor: roleInfo.color, color: roleInfo.color }}>
            {roleInfo.icon} {roleInfo.ar}
          </div>
        </header>

        {/* Messages */}
        <div className={styles.messages}>
          {messages.length === 0 && (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>💬</div>
              <h2 className={styles.emptyTitle}>أهلاً، {userName}</h2>
              <p className={styles.emptyDesc}>
                يمكنك السؤال بالعربية عن أي إجراء تشغيلي أو تعميم قانوني.
                <br />جميع الإجابات مدعومة بمصادر قابلة للتحقق.
              </p>
            </div>
          )}

          {messages.map(msg => (
            <div
              key={msg.id}
              className={`${styles.msgRow} ${msg.role === 'user' ? styles.msgRowUser : styles.msgRowAssistant}`}
            >
              {msg.role === 'user' && (
                <div className={styles.msgUser}>
                  <div className={styles.msgContent}>{msg.content}</div>
                  <div className={styles.msgMeta}>{msg.ts}</div>
                </div>
              )}

              {(msg.role === 'assistant' || msg.role === 'blocked' || msg.role === 'error') && (
                <div className={`${styles.msgAssistant} ${msg.role === 'blocked' ? styles.msgBlocked : ''} ${msg.role === 'error' ? styles.msgError : ''}`}>
                  {msg.role === 'assistant' && (
                    <div className={styles.msgHeader}>
                      <SparkleIcon animated={msg.latency_ms === undefined} />
                    </div>
                  )}
                  {(msg.role === 'blocked' || msg.role === 'error') && (
                    <div className={styles.msgHeader}>
                      <span className={styles.msgLabel}>
                        {msg.role === 'blocked' ? '🚫 محجوب' : '⚠️ خطأ'}
                      </span>
                    </div>
                  )}
                  <div className={styles.msgContent}>
                    {msg.role === 'assistant' ? (
                      <>
                        {msg.content.split(/(\[\d+\])/g).map((part, i) => {
                          const match = part.match(/\[(\d+)\]/);
                          if (match && msg.sources) {
                            const idx = parseInt(match[1]) - 1;
                            const src = msg.sources[idx];
                            if (src) {
                              return (
                                <button
                                  key={i}
                                  className={styles.inlineCitation}
                                  onClick={() => { setActiveSources(msg.sources!); setSelectedCitation(src); }}
                                >
                                  {part}
                                </button>
                              );
                            }
                          }
                          return <span key={i}>{part}</span>;
                        })}
                        {msg.latency_ms === undefined && (
                          <span className={styles.typewriterCursor}></span>
                        )}
                      </>
                    ) : (
                      msg.content
                    )}
                  </div>
                  {msg.sources && msg.sources.length > 0 && !msg.content.includes('صلاحيات حسابك مش بتسمح') && (
                    <div className={styles.citationRow}>
                      {msg.sources.map((src, i) => (
                        <button
                          key={src.id}
                          className={styles.citationChip}
                          onClick={() => { setActiveSources(msg.sources!); setSelectedCitation(src); }}
                        >
                          [{i + 1}] {src.doc_id} — ص {src.page_num}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className={styles.msgMeta}>
                    {msg.ts}
                    {msg.latency_ms !== undefined && (
                      <span className={styles.latency}>{(msg.latency_ms / 1000).toFixed(1)}ث</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className={styles.inputBar}>
          <textarea
            ref={inputRef}
            className={styles.textarea}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="اكتب سؤالك بالعربية… (Enter للإرسال، Shift+Enter لسطر جديد)"
            rows={1}
            disabled={loading}
            dir="rtl"
            id="chat-input"
          />
          <button
            className={styles.sendBtn}
            onClick={() => handleSend(input)}
            disabled={!input.trim() || loading}
            id="chat-send-btn"
            aria-label="إرسال"
          >
            {loading ? <span className={styles.sendSpinner} /> : '↑'}
          </button>
        </div>
      </main>

      {/* ── Citation panel ── */}
      <CitationPanel
        sources={activeSources}
        selectedCitation={selectedCitation}
        onSelectCitation={setSelectedCitation}
        onClose={() => { setActiveSources([]); setSelectedCitation(null); }}
      />
    </div>
  );
}
