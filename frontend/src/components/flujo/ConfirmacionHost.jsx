/**
 * ConfirmacionHost.jsx — La ventana que dibuja las preguntas de `confirmar.js`.
 *
 * Se monta UNA vez, en la raíz, al lado del `<Toaster />` y por el mismo
 * motivo. El por qué de todo esto está en `confirmar.js`.
 */
import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { C, HOJA, tarjeta, etiqueta, campo, ayuda } from './estilos';
import { Boton } from './index.jsx';
import { registrarHost } from './confirmar.js';

/**
 * Se monta UNA vez, en la raíz, al lado del `<Toaster />`.
 *
 * Mientras no hay pregunta abierta no dibuja nada.
 */
export default function ConfirmacionHost() {
  const [pedido, setPedido] = useState(null);
  const [texto, setTexto] = useState('');
  const cajaRef = useRef(null);

  // Cerrar se declara ANTES del efecto que lo usa. Al revés funcionaba —el
  // efecto corre después del dibujo—, pero deja una referencia a una constante
  // todavía sin inicializar, y eso se rompe en cuanto alguien mueve una línea.
  const cerrar = (valor) => {
    if (!pedido) return;
    pedido.resolver(valor);
    setPedido(null);
    setTexto('');
  };

  useEffect(() => registrarHost((opciones) => new Promise((resolver) => {
    setTexto(opciones.valorInicial || '');
    setPedido({ ...opciones, resolver });
  })), []);

  /* ── El teclado, mientras se pregunta ──────────────────────────────────
     Esto NO es sólo para que Escape cancele.

     El cuadro del navegador bloqueaba la página entera: mientras estaba
     abierto, nada más recibía teclas. Una ventana nuestra no bloquea nada, y
     varias pantallas de esta aplicación escuchan el teclado en `window`. La de
     revisión de KYC, sin ir más lejos, aprueba con «a» y rechaza con «r».

     Sin esto, abrir «¿Banear a este usuario?» encima de esa pantalla dejaría
     los atajos vivos: Escape cerraría la pregunta Y la ficha de atrás, y una
     «a» suelta aprobaría el KYC con la pregunta del baneo todavía en pantalla.
     Sería un cambio que EMPEORA lo que vino a arreglar.

     Se escucha en la fase de captura —antes que cualquier otro— y se corta ahí
     todo lo que no venga de un campo de esta ventana. */
  useEffect(() => {
    if (!pedido) return undefined;
    const alTeclear = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopImmediatePropagation();
        cerrar(null);
        return;
      }
      const dentro = cajaRef.current?.contains(e.target);
      const enUnCampo = ['TEXTAREA', 'INPUT'].includes(e.target?.tagName);
      if (!dentro || !enUnCampo) e.stopImmediatePropagation();
    };
    window.addEventListener('keydown', alTeclear, true);
    return () => window.removeEventListener('keydown', alTeclear, true);
  });

  if (!pedido) return null;

  const esTexto = pedido.clase === 'texto';
  const peligro = pedido.tono === 'peligro';
  const largoMaximo = pedido.largoMaximo || 300;
  const limpio = texto.trim();
  const faltaTexto = esTexto && !pedido.opcional && !limpio;

  return (
    <div className="env" role="dialog" aria-modal="true" aria-labelledby="cf-titulo"
      style={{
        position: 'fixed', inset: 0, zIndex: 3000, padding: '16px',
        background: 'rgba(16,24,40,.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'Inter, -apple-system, Segoe UI, Roboto, sans-serif',
      }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) cerrar(null); }}>
      <style>{HOJA}</style>

      <div ref={cajaRef} data-testid="confirmacion"
        style={{ ...tarjeta, padding: '22px', width: '100%', maxWidth: '440px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', marginBottom: '14px' }}>
          <span style={{
            width: '38px', height: '38px', borderRadius: '11px', flexShrink: 0,
            background: peligro ? C.errorSuave : C.marcaSuave,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <AlertTriangle size={18} color={peligro ? C.error : C.marca} />
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id="cf-titulo" style={{
              margin: 0, fontSize: '16.5px', fontWeight: 700, color: C.tinta, lineHeight: 1.35,
            }}>
              {pedido.titulo}
            </h2>
            {pedido.detalle ? (
              <p style={{ margin: '5px 0 0 0', fontSize: '13.5px', color: C.suave, lineHeight: 1.55 }}>
                {pedido.detalle}
              </p>
            ) : null}
          </div>
          <button type="button" onClick={() => cerrar(null)} aria-label="Cancelar"
            style={{
              border: 'none', background: 'none', padding: '4px', flexShrink: 0,
              color: C.tenue, cursor: 'pointer', display: 'inline-flex',
            }}>
            <X size={17} />
          </button>
        </div>

        {esTexto ? (
          <div style={{ marginBottom: '16px' }}>
            {pedido.etiqueta ? (
              <label style={etiqueta} htmlFor="cf-texto">{pedido.etiqueta}</label>
            ) : null}
            <textarea id="cf-texto" className="env-campo" rows={3} autoFocus
              placeholder={pedido.placeholder || ''} value={texto}
              maxLength={largoMaximo}
              onChange={(e) => setTexto(e.target.value)}
              style={{ ...campo, resize: 'vertical', lineHeight: 1.5 }} />
            <p style={ayuda}>
              {pedido.opcional ? 'Podés dejarlo vacío. ' : ''}
              {texto.length}/{largoMaximo}
            </p>
          </div>
        ) : null}

        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <Boton onClick={() => cerrar(null)} testid="confirmacion-no">
            {pedido.cancelar || 'Cancelar'}
          </Boton>
          <Boton tipo={peligro ? 'peligro' : 'primario'} disabled={faltaTexto}
            testid="confirmacion-si"
            onClick={() => cerrar(esTexto ? limpio.slice(0, largoMaximo) : true)}>
            {pedido.accion || 'Confirmar'}
          </Boton>
        </div>
      </div>
    </div>
  );
}
