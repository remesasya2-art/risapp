/**
 * SelectorDeApariencia — el botón del sol y la luna, con sus tres opciones.
 *
 * POR QUE UN MENU Y NO UN BOTON QUE VA ROTANDO
 *
 *   Con tres estados, un botón que rota obliga a apretar hasta dar con el que
 *   se quiere, y «automático» no se distingue a simple vista de «claro» si es
 *   de día. El menú muestra las tres y marca la elegida, como el iPhone.
 */
import { useEffect, useRef, useState } from 'react';
import { Check, Monitor, Moon, Sun } from 'lucide-react';
import { useTema } from '../../contexts/TemaContext';

const OPCIONES = [
  { valor: 'auto', texto: 'Automático', icono: <Monitor size={16} /> },
  { valor: 'claro', texto: 'Claro', icono: <Sun size={16} /> },
  { valor: 'oscuro', texto: 'Oscuro', icono: <Moon size={16} /> },
];

// `cuadrado`: en el panel de administración el botón va al lado de la campana
// y de «Actualizar», que son cuadrados grises. El círculo de vidrio de la
// portada ahí casi no se veía y parecía de otra aplicación.
export default function SelectorDeApariencia({ cuadrado = false }) {
  const { apariencia, tema, elegir } = useTema();
  const [abierto, setAbierto] = useState(false);
  const caja = useRef(null);

  useEffect(() => {
    if (!abierto) return undefined;
    const fuera = (e) => { if (!caja.current?.contains(e.target)) setAbierto(false); };
    const tecla = (e) => { if (e.key === 'Escape') setAbierto(false); };
    document.addEventListener('mousedown', fuera);
    document.addEventListener('keydown', tecla);
    return () => {
      document.removeEventListener('mousedown', fuera);
      document.removeEventListener('keydown', tecla);
    };
  }, [abierto]);

  const actual = OPCIONES.find((o) => o.valor === apariencia) || OPCIONES[0];

  return (
    <div ref={caja} style={{ position: 'relative' }}>
      <button
        type="button"
        className={cuadrado ? undefined : 't-vidrio t-vidrio-plano'}
        aria-label={`Apariencia: ${actual.texto}`}
        title={`Apariencia: ${actual.texto}`}
        aria-haspopup="menu"
        aria-expanded={abierto}
        data-testid="selector-de-apariencia"
        onClick={() => setAbierto((v) => !v)}
        style={{
          width: 40, height: 40, borderRadius: '50%', display: 'grid', placeItems: 'center',
          color: 'var(--t-texto)', cursor: 'pointer', padding: 0,
          ...(cuadrado ? {
            borderRadius: '12px', border: 'none',
            backgroundColor: 'var(--en-oscuro-superficie-2, #f3f4f6)',
            color: 'var(--en-oscuro-texto, #374151)',
          } : {}),
        }}
      >
        {tema === 'oscuro' ? <Moon size={18} /> : <Sun size={18} />}
      </button>
      {abierto && (
        <div
          role="menu"
          aria-label="Apariencia"
          className="t-vidrio"
          style={{
            position: 'absolute', right: 0, top: 48, zIndex: 50, minWidth: 190,
            borderRadius: 16, padding: 6, background: 'var(--t-vidrio-fuerte)',
          }}
        >
          {OPCIONES.map((o) => (
            <button
              key={o.valor}
              type="button"
              role="menuitemradio"
              aria-checked={apariencia === o.valor}
              data-testid={`apariencia-${o.valor}`}
              onClick={() => { elegir(o.valor); setAbierto(false); }}
              style={{
                display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                padding: '10px 12px', borderRadius: 10, border: 0, background: 'transparent',
                color: 'var(--t-texto)', font: 'inherit', fontSize: 15, cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <span style={{ color: 'var(--t-texto-2)', display: 'grid' }}>{o.icono}</span>
              <span style={{ flex: 1 }}>{o.texto}</span>
              {apariencia === o.valor && <Check size={16} style={{ color: 'var(--t-acento)' }} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
