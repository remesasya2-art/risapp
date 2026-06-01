import { useEffect, useState, useCallback } from 'react';
import { X, ZoomIn, ZoomOut, RotateCw, Download, RefreshCw } from 'lucide-react';

/**
 * Fullscreen image lightbox with zoom in/out, rotation 90°, ESC to close.
 *
 * Props:
 *   images: [{ url, label }]
 *   index: number (initial)
 *   onClose: () => void
 */
export default function ImageLightbox({ images = [], index = 0, onClose }) {
  const [currentIndex, setCurrentIndex] = useState(index);
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0, ox: 0, oy: 0 });

  const current = images[currentIndex];

  const reset = useCallback(() => {
    setScale(1);
    setRotation(0);
    setPan({ x: 0, y: 0 });
  }, []);

  useEffect(() => {
    reset();
  }, [currentIndex, reset]);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
      else if (e.key === '+' || e.key === '=') setScale((s) => Math.min(s + 0.25, 5));
      else if (e.key === '-' || e.key === '_') setScale((s) => Math.max(s - 0.25, 0.25));
      else if (e.key.toLowerCase() === 'r') setRotation((r) => (r + 90) % 360);
      else if (e.key === 'ArrowRight' && images.length > 1) setCurrentIndex((i) => (i + 1) % images.length);
      else if (e.key === 'ArrowLeft' && images.length > 1) setCurrentIndex((i) => (i - 1 + images.length) % images.length);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, images.length]);

  // Lock body scroll while open
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  const handleWheel = (e) => {
    if (e.ctrlKey || e.metaKey) e.preventDefault();
    const delta = -e.deltaY * 0.0015;
    setScale((s) => Math.min(Math.max(s + delta, 0.25), 5));
  };

  const handleMouseDown = (e) => {
    if (scale <= 1) return;
    setDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY, ox: pan.x, oy: pan.y });
  };
  const handleMouseMove = (e) => {
    if (!dragging) return;
    setPan({ x: dragStart.ox + (e.clientX - dragStart.x), y: dragStart.oy + (e.clientY - dragStart.y) });
  };
  const handleMouseUp = () => setDragging(false);

  const download = () => {
    if (!current?.url) return;
    const a = document.createElement('a');
    a.href = current.url;
    a.download = (current.label || 'imagen').replace(/\s+/g, '_') + '.jpg';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  if (!current) return null;

  const overlayStyle = {
    position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.92)',
    zIndex: 99999, display: 'flex', flexDirection: 'column',
  };
  const toolbarBtn = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: '40px', height: '40px', borderRadius: '10px',
    backgroundColor: 'rgba(255,255,255,0.08)', color: 'white',
    border: '1px solid rgba(255,255,255,0.12)', cursor: 'pointer',
    transition: 'background 0.15s',
  };
  const toolbarBtnHover = (e, on) => { e.currentTarget.style.backgroundColor = on ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.08)'; };

  return (
    <div
      style={overlayStyle}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      role="dialog"
      aria-modal="true"
    >
      {/* Top bar */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '14px 20px', color: 'white',
        background: 'linear-gradient(to bottom, rgba(0,0,0,0.6), transparent)'
      }}>
        <div>
          <div style={{ fontSize: '15px', fontWeight: 600 }}>{current.label || 'Imagen'}</div>
          {images.length > 1 && (
            <div style={{ fontSize: '12px', color: 'rgba(255,255,255,0.6)', marginTop: '2px' }}>
              {currentIndex + 1} / {images.length}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button title="Reducir (−)" style={toolbarBtn} onMouseEnter={(e)=>toolbarBtnHover(e,true)} onMouseLeave={(e)=>toolbarBtnHover(e,false)} onClick={() => setScale((s) => Math.max(s - 0.25, 0.25))}>
            <ZoomOut size={20} />
          </button>
          <button title="Ampliar (+)" style={toolbarBtn} onMouseEnter={(e)=>toolbarBtnHover(e,true)} onMouseLeave={(e)=>toolbarBtnHover(e,false)} onClick={() => setScale((s) => Math.min(s + 0.25, 5))}>
            <ZoomIn size={20} />
          </button>
          <button title="Rotar 90° (R)" style={toolbarBtn} onMouseEnter={(e)=>toolbarBtnHover(e,true)} onMouseLeave={(e)=>toolbarBtnHover(e,false)} onClick={() => setRotation((r) => (r + 90) % 360)}>
            <RotateCw size={20} />
          </button>
          <button title="Restablecer" style={toolbarBtn} onMouseEnter={(e)=>toolbarBtnHover(e,true)} onMouseLeave={(e)=>toolbarBtnHover(e,false)} onClick={reset}>
            <RefreshCw size={20} />
          </button>
          <button title="Descargar" style={toolbarBtn} onMouseEnter={(e)=>toolbarBtnHover(e,true)} onMouseLeave={(e)=>toolbarBtnHover(e,false)} onClick={download}>
            <Download size={20} />
          </button>
          <button title="Cerrar (ESC)" style={toolbarBtn} onMouseEnter={(e)=>toolbarBtnHover(e,true)} onMouseLeave={(e)=>toolbarBtnHover(e,false)} onClick={onClose}>
            <X size={20} />
          </button>
        </div>
      </div>

      {/* Image area */}
      <div
        style={{
          flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          overflow: 'hidden', cursor: scale > 1 ? (dragging ? 'grabbing' : 'grab') : 'default',
        }}
        onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
        onMouseDown={handleMouseDown}
      >
        <img
          src={current.url}
          alt={current.label || 'imagen'}
          draggable={false}
          style={{
            maxWidth: '92vw', maxHeight: '78vh',
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale}) rotate(${rotation}deg)`,
            transition: dragging ? 'none' : 'transform 0.15s ease',
            userSelect: 'none',
            boxShadow: '0 10px 40px rgba(0,0,0,0.4)',
            borderRadius: '8px',
            backgroundColor: '#fff',
            imageOrientation: 'from-image',
          }}
        />
      </div>

      {/* Thumbnails (if multiple) */}
      {images.length > 1 && (
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', padding: '14px', background: 'linear-gradient(to top, rgba(0,0,0,0.6), transparent)' }}>
          {images.map((img, i) => (
            <button
              key={i}
              onClick={() => setCurrentIndex(i)}
              style={{
                width: '52px', height: '52px', borderRadius: '8px',
                overflow: 'hidden', cursor: 'pointer', padding: 0,
                border: i === currentIndex ? '2px solid #6366f1' : '2px solid rgba(255,255,255,0.2)',
                opacity: i === currentIndex ? 1 : 0.6, background: '#000',
              }}
            >
              <img src={img.url} alt={img.label} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </button>
          ))}
        </div>
      )}

      {/* Hint */}
      <div style={{
        position: 'absolute', bottom: '12px', right: '16px',
        fontSize: '11px', color: 'rgba(255,255,255,0.45)'
      }}>
        ESC cerrar · + / − zoom · R rotar · ← → navegar
      </div>
    </div>
  );
}
