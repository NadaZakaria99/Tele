import { useState } from 'react';
import type { SourceChunk } from './api';
import styles from './CitationPanel.module.css';

interface CitationPanelProps {
  sources: SourceChunk[];
  selectedCitation: SourceChunk | null;
  onSelectCitation: (src: SourceChunk) => void;
  onClose: () => void;
}

const DOC_LABELS: Record<string, string> = {
  rtgs:             'دليل إجراءات RTGS',
  legal_circular_1: 'تعميم قانوني رقم 1',
  legal_circular_2: 'تعميم قانوني رقم 2',
};

function scoreColor(score?: number): string {
  if (score === undefined) return 'var(--text-muted)';
  if (score > 6) return 'var(--green)';
  if (score > 2) return 'var(--yellow)';
  return 'var(--red)';
}

function scoreLabel(score?: number): string {
  if (score === undefined) return '—';
  if (score > 6) return 'عالية';
  if (score > 2) return 'متوسطة';
  return 'منخفضة';
}

export default function CitationPanel({ sources, selectedCitation, onSelectCitation, onClose }: CitationPanelProps) {
  const [imgError, setImgError] = useState(false);
  const [imgLoading, setImgLoading] = useState(true);
  const [viewMode, setViewMode] = useState<'image' | 'text'>('image');

  if (!sources.length) return null;

  const active = selectedCitation ?? sources[0];

  return (
    <aside className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <span className={styles.panelTitle}>المصادر والمراجع</span>
          <span className={styles.panelCount}>{sources.length} مقتطفات</span>
        </div>
        <button className={styles.closeBtn} onClick={onClose} aria-label="إغلاق">✕</button>
      </div>

      {/* Source list */}
      <div className={styles.sourceList}>
        {sources.map((src, i) => (
          <button
            key={src.id}
            className={`${styles.sourceItem} ${active.id === src.id ? styles.sourceItemActive : ''}`}
            onClick={() => { onSelectCitation(src); setImgError(false); setImgLoading(true); }}
          >
            <div className={styles.sourceItemTop}>
              <span className={styles.sourceIndex}>[{i + 1}]</span>
              <span className={styles.sourceDoc}>{DOC_LABELS[src.doc_id] ?? src.doc_id}</span>
              <span className={styles.sourcePage}>ص {src.page_num}</span>
            </div>
            <div className={styles.sourceScore} style={{ color: scoreColor(src.reranker_score) }}>
              ● ملاءمة {scoreLabel(src.reranker_score)}
            </div>
            <div className={styles.sourcePreview}>
              {src.content.replace(/<[^>]*>/g, '').slice(0, 90)}…
            </div>
          </button>
        ))}
      </div>

      {/* Detail view for selected citation */}
      <div className={styles.detail}>
        <div className={styles.detailHeader}>
          <div className={styles.detailTitleWrapper}>
            <div className={styles.detailDoc}>
              📄 {DOC_LABELS[active.doc_id] ?? active.doc_id}
            </div>
            <div className={styles.detailPage}>صفحة {active.page_num}</div>
          </div>
        </div>

        {/* View Mode Tabs */}
        <div className={styles.tabs}>
          <button 
            className={`${styles.tabBtn} ${viewMode === 'image' ? styles.tabBtnActive : ''}`}
            onClick={() => setViewMode('image')}
          >
            🖼️ عرض الصورة
          </button>
          <button 
            className={`${styles.tabBtn} ${viewMode === 'text' ? styles.tabBtnActive : ''}`}
            onClick={() => setViewMode('text')}
          >
            📝 عرض النص
          </button>
        </div>

        {/* Content Area */}
        <div className={styles.contentArea}>
          {viewMode === 'image' ? (
            active.crop_url ? (
              <div className={styles.imageContainer}>
                {imgLoading && !imgError && (
                  <div className={styles.imgSkeleton}>
                    <div className={styles.imgShimmer} />
                  </div>
                )}
                {!imgError ? (
                  <img
                    src={active.crop_url}
                    alt={`مقتطف من ${active.doc_id} صفحة ${active.page_num}`}
                    className={styles.citationImg}
                    style={{ display: imgLoading ? 'none' : 'block' }}
                    onLoad={() => setImgLoading(false)}
                    onError={() => { setImgError(true); setImgLoading(false); }}
                  />
                ) : (
                  <div className={styles.imgError}>
                    <span>⚠️</span>
                    <span>تعذّر تحميل الصورة</span>
                  </div>
                )}
              </div>
            ) : (
              <div className={styles.noImageMsg}>لا توجد صورة بصرية لهذا المقتطف.</div>
            )
          ) : (
            <div className={styles.textContent}>
              <div
                className={styles.textBody}
                dangerouslySetInnerHTML={{
                  __html: active.content.startsWith('<') ? active.content : `<p>${active.content}</p>`,
                }}
              />
            </div>
          )}
        </div>

        {/* Action Button */}
        {active.crop_url && (
          <a href={active.crop_url} target="_blank" rel="noopener noreferrer" className={styles.actionBtn}>
            عرض الوثيقة الأصلية ↗
          </a>
        )}
      </div>
    </aside>
  );
}
