import { useState } from 'react';
import type { SourceChunk } from '../types/api';

interface Props {
  sources: SourceChunk[];
}


export function CitationsPanel({ sources }: Props) {
  const [open, setOpen] = useState(false);
  const [lightbox, setLightbox] = useState<{ url: string; alt: string } | null>(null);

  if (!sources.length) return null;

  const blockTypeLabel: Record<string, string> = {
    table: 'جدول',
    text: 'نص',
    header: 'عنوان',
    figure: 'شكل',
    list: 'قائمة',
  };

  return (
    <>
      <button
        className="citations-toggle"
        onClick={() => setOpen(v => !v)}
        id="citations-toggle-btn"
        aria-expanded={open}
      >
        <span>{open ? '▲' : '▼'}</span>
        <span>المصادر والمراجع</span>
        <span className="citations-count">{sources.length}</span>
      </button>

      {open && (
        <div className="citations-panel" role="list" aria-label="قائمة المصادر">
          {sources.map((src) => (
            <div key={src.id} className="citation-card" role="listitem">
              <div className="citation-header">
                <div className="citation-doc">
                  <div className="citation-badge">{src.id + 1}</div>
                  <div className="citation-meta">
                    <strong>{src.doc_id.toUpperCase().replace(/_/g, ' ')}</strong>
                    <span>صفحة {src.page_num}</span>
                  </div>
                </div>
                <span className="citation-type">
                  {blockTypeLabel[src.block_type] || src.block_type}
                </span>
              </div>

              <div className="citation-body">
                {/* Text excerpt */}
                <div
                  className="citation-text"
                  dangerouslySetInnerHTML={{ __html: src.content.slice(0, 300) }}
                />

                {/* Crop image */}
                {src.crop_url && (
                  <div
                    className="citation-crop"
                    onClick={() =>
                      setLightbox({
                        url: src.crop_url!,
                        alt: `مقتطف من ${src.doc_id} صفحة ${src.page_num}`,
                      })
                    }
                    role="button"
                    tabIndex={0}
                    aria-label="عرض الصورة بحجم كامل"
                    id={`citation-crop-${src.id}`}
                    onKeyDown={e => e.key === 'Enter' && setLightbox({ url: src.crop_url!, alt: `مقتطف من ${src.doc_id} صفحة ${src.page_num}` })}
                  >
                    <img
                      src={src.crop_url}
                      alt={`مقتطف بصري — ${src.doc_id} ص${src.page_num}`}
                      loading="lazy"
                    />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div
          className="lightbox-overlay"
          onClick={() => setLightbox(null)}
          role="dialog"
          aria-modal="true"
          aria-label="عرض الصورة"
        >
          <div className="lightbox-content" onClick={e => e.stopPropagation()}>
            <button
              className="lightbox-close"
              onClick={() => setLightbox(null)}
              aria-label="إغلاق"
              id="lightbox-close-btn"
            >
              ×
            </button>
            <img src={lightbox.url} alt={lightbox.alt} />
          </div>
        </div>
      )}
    </>
  );
}
