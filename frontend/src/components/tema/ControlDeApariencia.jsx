/**
 * ControlDeApariencia — la fila «Apariencia» del perfil: Automático, Claro,
 * Oscuro, las tres a la vista, como en los Ajustes del iPhone.
 *
 * En el perfil va a la vista y no dentro de un menú (como el botón del sol y
 * la luna de la portada): acá la persona vino justamente a configurar, y un
 * menú escondería lo que vino a buscar.
 *
 * Lo que elige se guarda en su cuenta; ver contexts/TemaContext.jsx.
 */
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTema } from '../../contexts/TemaContext';
import { C, tarjeta } from '../flujo/estilos';

const OPCIONES = [
  { valor: 'auto', texto: 'Automático', icono: <Monitor size={17} /> },
  { valor: 'claro', texto: 'Claro', icono: <Sun size={17} /> },
  { valor: 'oscuro', texto: 'Oscuro', icono: <Moon size={17} /> },
];

export default function ControlDeApariencia() {
  const { apariencia, elegir } = useTema();

  return (
    <section style={{ ...tarjeta, padding: '18px 20px', marginBottom: '16px' }} data-testid="apariencia">
      <span style={{ display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.tinta }}>
        Apariencia
      </span>
      <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, margin: '1px 0 12px' }}>
        Se guarda en tu cuenta: la ves igual en cualquier aparato.
      </span>
      <div
        role="radiogroup"
        aria-label="Apariencia"
        style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px',
          padding: '4px', borderRadius: '12px', background: C.fondo,
        }}
      >
        {OPCIONES.map((o) => {
          const elegida = apariencia === o.valor;
          return (
            <button
              key={o.valor}
              type="button"
              role="radio"
              aria-checked={elegida}
              data-testid={`apariencia-perfil-${o.valor}`}
              onClick={() => elegir(o.valor)}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
                padding: '10px 6px', borderRadius: '9px', cursor: 'pointer',
                border: elegida ? `1px solid ${C.linea}` : '1px solid transparent',
                background: elegida ? C.lienzo : 'transparent',
                boxShadow: elegida ? '0 1px 3px rgba(16,24,40,.10)' : 'none',
                color: elegida ? C.marca : C.suave,
                fontSize: '13px', fontWeight: elegida ? 700 : 500,
              }}
            >
              {o.icono}
              {o.texto}
            </button>
          );
        })}
      </div>
    </section>
  );
}
