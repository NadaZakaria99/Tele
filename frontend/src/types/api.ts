// API types — mirror the rag_service Pydantic models exactly

export type Role = 'teller' | 'legal_counsel' | 'manager';

export interface SourceChunk {
  id: number;
  doc_id: string;
  page_num: number;
  content: string;
  crop_url: string | null;
  page_image_url: string | null;
  block_type: string;
}

export interface ChatResponse {
  answer: string;
  sources: SourceChunk[];
  blocked: boolean;
  latency_ms: number;
}

export interface ChatRequest {
  query: string;
  role: Role;
}

// UI-only types
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceChunk[];
  blocked?: boolean;
  latency_ms?: number;
  timestamp: Date;
  loading?: boolean;
}

export interface RoleConfig {
  id: Role;
  label: string;
  description: string;
  color: string;
  emoji: string;
}

export const ROLES: RoleConfig[] = [
  {
    id: 'teller',
    label: 'موظف صراف',
    description: 'إجراءات التشغيل',
    color: '#3B82F6',
    emoji: '🏦',
  },
  {
    id: 'legal_counsel',
    label: 'مستشار قانوني',
    description: 'التعميمات القانونية',
    color: '#A855F7',
    emoji: '⚖️',
  },
  {
    id: 'manager',
    label: 'مدير',
    description: 'جميع الوثائق',
    color: '#C9A84C',
    emoji: '👔',
  },
];

export const EXAMPLE_QUESTIONS: Record<Role, string[]> = {
  teller: [
    'ما هي خطوات تنفيذ تحويل RTGS؟',
    'ما هي حدود السحب اليومي من الصراف الآلي؟',
    'كيف يتم التعامل مع الأوراق المالية المشبوهة؟',
  ],
  legal_counsel: [
    'ما هي متطلبات الامتثال لقانون مكافحة غسيل الأموال؟',
    'ما هي شروط فتح حساب الشركات؟',
    'ما هي اشتراطات البنك المركزي بشأن الائتمان؟',
  ],
  manager: [
    'ما هي سياسات منح الائتمان للشركات الصغيرة؟',
    'ما هي إجراءات إغلاق الفروع؟',
    'ما هي ضوابط نسبة الديون المتعثرة؟',
  ],
};
