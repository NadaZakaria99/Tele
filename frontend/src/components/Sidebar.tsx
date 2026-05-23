import type { Role, RoleConfig } from '../types/api';
import { ROLES } from '../types/api';

interface Props {
  activeRole: Role;
  onRoleChange: (role: Role) => void;
  onNewChat: () => void;
}

export function Sidebar({ activeRole, onRoleChange, onNewChat }: Props) {


  return (
    <aside className="sidebar" role="navigation" aria-label="لوحة التنقل">

      {/* Logo */}
      <div className="sidebar-logo">
        <div className="logo-icon" aria-hidden="true">🏛️</div>
        <div className="logo-text">
          <h1>المساعد المعرفي</h1>
          <p>البنك الأهلي المصري</p>
        </div>
      </div>

      {/* Role Selector */}
      <div className="role-section">
        <h2 id="role-section-label">الدور الوظيفي</h2>
        <div className="role-cards" role="radiogroup" aria-labelledby="role-section-label">
          {ROLES.map((r: RoleConfig) => (
            <button
              key={r.id}
              className={`role-card${activeRole === r.id ? ' active' : ''}`}
              style={{ '--role-color': r.color } as React.CSSProperties}
              onClick={() => onRoleChange(r.id)}
              role="radio"
              aria-checked={activeRole === r.id}
              id={`role-btn-${r.id}`}
            >
              <div className="role-dot" />
              <div className="role-info">
                <span className="role-name">{r.emoji} {r.label}</span>
                <span className="role-desc">{r.description}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* New Chat */}
      <button
        className="new-chat-btn"
        onClick={onNewChat}
        id="new-chat-btn"
        aria-label="بدء محادثة جديدة"
      >
        <span>+</span>
        <span>محادثة جديدة</span>
      </button>

      {/* Footer */}
      <div className="sidebar-footer">
        <p>مدعوم بـ NVIDIA NIMs</p>
        <p style={{ marginTop: '4px', fontSize: '10px' }}>الإجابات للاستخدام الداخلي فقط</p>
      </div>
    </aside>
  );
}
