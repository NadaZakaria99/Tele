import { useState, type KeyboardEvent, useRef, useEffect } from 'react';

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function MessageInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const handleSend = () => {
    if (!value.trim() || disabled) return;
    onSend(value.trim());
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="input-area">
      <div className="input-wrapper">
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          title="إرسال"
          aria-label="إرسال الرسالة"
          id="send-message-btn"
        >
          {disabled ? '⏳' : '↑'}
        </button>
        <textarea
          ref={textareaRef}
          id="chat-input"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKey}
          placeholder="اكتب سؤالك هنا... (Enter للإرسال، Shift+Enter لسطر جديد)"
          disabled={disabled}
          rows={1}
          aria-label="مربع إدخال السؤال"
        />
      </div>
      <p className="input-hint">
        الإجابات مبنية على وثائق البنك الأهلي المصري الرسمية فقط
      </p>
    </div>
  );
}
