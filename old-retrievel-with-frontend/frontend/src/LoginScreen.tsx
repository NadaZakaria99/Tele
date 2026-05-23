import { useState, useEffect } from 'react';
import type { UserRole } from './api';
import { checkHealth } from './api';
import styles from './LoginScreen.module.css';

interface LoginScreenProps {
  onLogin: (role: UserRole, name: string) => void;
}

const ROLES = [
  {
    id: 'teller' as UserRole,
    icon: '🏦',
    titleAr: 'موظف خدمة العملاء',
    titleEn: 'Branch Teller',
    descAr: 'استعلام عن الإجراءات التشغيلية اليومية والدوريات العامة',
    access: ['الإجراءات التشغيلية', 'دليل المنتجات', 'RTGS'],
    color: '#4A9EFF',
    glow: 'rgba(74,158,255,0.2)',
  },
  {
    id: 'legal_counsel' as UserRole,
    icon: '⚖️',
    titleAr: 'المستشار القانوني',
    titleEn: 'Senior Legal Counsel',
    descAr: 'الوصول الكامل بما يشمل التعميمات القانونية والدوريات السرية',
    access: ['جميع الوثائق', 'التعميمات القانونية', 'الدوريات المقيدة'],
    color: '#C9A84C',
    glow: 'rgba(201,168,76,0.2)',
  },
];

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [health, setHealth] = useState<{ ok: boolean; entities?: number } | null>(null);
  const [selectedRole, setSelectedRole] = useState<UserRole | null>(null);
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    checkHealth()
      .then(h => setHealth({ ok: true, entities: h.collection_entities }))
      .catch(() => setHealth({ ok: false }));
  }, []);

  const handleLogin = () => {
    if (!selectedRole || !name.trim()) return;
    setLoading(true);
    setTimeout(() => onLogin(selectedRole, name.trim()), 600);
  };

  return (
    <div className={styles.container}>
      {/* Animated background grid */}
      <div className={styles.grid} aria-hidden="true" />

      {/* Glow orbs */}
      <div className={styles.orb1} aria-hidden="true" />
      <div className={styles.orb2} aria-hidden="true" />

      <div className={styles.card}>
        {/* Logo & Header */}
        <div className={styles.header}>
          <img 
            src="/nbe_logo.png" 
            alt="البنك الأهلي المصري" 
            className={styles.headerLogoImage} 
          />
        </div>

        {/* System status */}
        <div className={styles.statusBar}>
          <span className={`${styles.dot} ${health?.ok ? styles.dotGreen : health === null ? styles.dotPulse : styles.dotRed}`} />
          <span className={styles.statusText}>
            {health === null ? 'جارٍ الاتصال بالنظام…' :
              health.ok ? 'النظام جاهز للاستخدام' :
                'تعذّر الاتصال بالخادم'}
          </span>
        </div>

        <div className={styles.divider} />

        {/* Name input */}
        <div className={styles.section}>
          <label className={styles.label} htmlFor="emp-name">بماذا تحب أن أناديك اليوم؟</label>
          <input
            id="emp-name"
            className={styles.input}
            type="text"
            placeholder="أدخل اسمك…"
            value={name}
            onChange={e => setName(e.target.value)}
            dir="rtl"
          />
        </div>

        {/* Role selection */}
        <div className={styles.section}>
          <label className={styles.label}>نوع الصلاحية</label>
          <div className={styles.roles}>
            {ROLES.map(role => (
              <button
                key={role.id}
                className={`${styles.roleCard} ${selectedRole === role.id ? styles.roleCardSelected : ''}`}
                style={selectedRole === role.id ? {
                  borderColor: role.color,
                  boxShadow: `0 0 24px ${role.glow}`,
                } : {}}
                onClick={() => setSelectedRole(role.id)}
                aria-pressed={selectedRole === role.id}
              >
                <div className={styles.roleIcon}>{role.icon}</div>
                <div className={styles.roleInfo}>
                  <div className={styles.roleTitle} style={selectedRole === role.id ? { color: role.color } : {}}>
                    {role.titleAr}
                  </div>
                  <div className={styles.roleSubtitle}>{role.titleEn}</div>
                  <div className={styles.roleDesc}>{role.descAr}</div>
                  {selectedRole === role.id && (
                    <div className={styles.accessBadges}>
                      {role.access.map(a => (
                        <span key={a} className={styles.accessBadge} style={{ borderColor: role.color, color: role.color }}>
                          {a}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {selectedRole === role.id && (
                  <div className={styles.checkmark} style={{ background: role.color }}>✓</div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Login button */}
        <button
          className={`${styles.loginBtn} ${loading ? styles.loginBtnLoading : ''}`}
          disabled={!selectedRole || !name.trim() || loading || !health?.ok}
          onClick={handleLogin}
          id="login-submit-btn"
        >
          {loading ? (
            <><span className={styles.spinner} /> جارٍ تسجيل الدخول…</>
          ) : (
            'دخول إلى النظام'
          )}
        </button>
      </div>
    </div>
  );
}
