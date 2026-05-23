import { useState, useEffect, useRef } from 'react';
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
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    checkHealth()
      .then(h => setHealth({ ok: true, entities: h.collection_entities }))
      .catch(() => setHealth({ ok: false }));
  }, []);

  // Particle Canvas Effect
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let mouse = { x: 0, y: 0 };

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', resize);
    resize();

    const handleMouseMove = (e: MouseEvent) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };
    window.addEventListener('mousemove', handleMouseMove);

    class Particle {
      x: number; y: number; size: number; speedX: number; speedY: number;
      constructor() {
        this.x = Math.random() * canvas!.width;
        this.y = Math.random() * canvas!.height;
        this.size = Math.random() * 2 + 0.5;
        this.speedX = Math.random() * 1 - 0.5;
        this.speedY = Math.random() * 1 - 0.5;
      }
      update() {
        this.x += this.speedX;
        this.y += this.speedY;

        const dx = mouse.x - this.x;
        const dy = mouse.y - this.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < 100) {
          this.x -= dx * 0.01;
          this.y -= dy * 0.01;
        }

        if (this.x > canvas!.width) this.x = 0;
        if (this.x < 0) this.x = canvas!.width;
        if (this.y > canvas!.height) this.y = 0;
        if (this.y < 0) this.y = canvas!.height;
      }
      draw() {
        if (!ctx) return;
        ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    const particles: Particle[] = Array.from({ length: 45 }, () => new Particle());

    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach((p, index) => {
        p.update();
        p.draw();
        for (let j = index; j < particles.length; j++) {
          const dx = p.x - particles[j].x;
          const dy = p.y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.strokeStyle = `rgba(255, 255, 255, ${0.1 * (1 - dist / 120)})`;
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      });
      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', handleMouseMove);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  const handleLogin = () => {
    if (!selectedRole || !name.trim()) return;
    setLoading(true);
    setTimeout(() => onLogin(selectedRole, name.trim()), 600);
  };

  const handleCardMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = (y - centerY) / 10;
    const rotateY = -(x - centerX) / 20;
    card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
  };

  const handleCardMouseLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.transform = '';
  };

  return (
    <div className={styles.container}>
      {/* Animated background grid */}
      <div className={styles.grid} aria-hidden="true" />

      {/* Particle Canvas */}
      <canvas ref={canvasRef} className={styles.particleCanvas} aria-hidden="true" />

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
          <label className={styles.mainLabel} htmlFor="emp-name">بماذا تحب أن أناديك اليوم؟</label>
          <div className={styles.inputWrapper}>
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
        </div>

        {/* Role selection */}
        <div className={styles.section}>
          <label className={styles.subLabel}>نوع الصلاحية</label>
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
                onMouseMove={handleCardMouseMove}
                onMouseLeave={handleCardMouseLeave}
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

        {/* Footer */}
        <div className={styles.footer} lang='en' dir='ltr'>
          © 2026 <b>EFADA Technology</b>. All Rights Reserved.
        </div>
      </div>
    </div>
  );
}
