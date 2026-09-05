/**
 * Support.jsx — La pantalla de Soporte, la del menú.
 *
 * Es la MISMA pieza que el botón de la esquina, con más lugar: dibuja
 * `components/soporte/CasosDelCliente`. Antes eran dos códigos distintos para
 * el mismo trabajo, y se habían separado —la pantalla no mostraba la
 * calificación, el botón flotante no mostraba el historial—.
 */
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, LifeBuoy } from 'lucide-react';
import NotificationBell from '../components/NotificationBell';
import CasosDelCliente from '../components/soporte/CasosDelCliente';
import { C, HOJA, tarjeta, ayuda } from '../components/flujo/estilos';

export default function Support() {
  const navigate = useNavigate();

  // `navigate(-1)` a secas se va de la aplicación cuando se entró directo a
  // esta dirección. Es la misma corrección que en el perfil.
  const volver = () => {
    if (window.history.length > 1) navigate(-1);
    else navigate('/');
  };

  return (
    <div className="env" data-testid="support-page" style={{
      minHeight: '100vh', background: C.fondo,
      fontFamily: 'Inter, -apple-system, Segoe UI, Roboto, sans-serif',
    }}>
      <style>{HOJA}</style>

      <header style={{
        background: C.lienzo, borderBottom: `1px solid ${C.linea}`,
        position: 'sticky', top: 0, zIndex: 20,
      }}>
        <div style={{
          maxWidth: '720px', margin: '0 auto', padding: '0 16px', height: '60px',
          display: 'flex', alignItems: 'center', gap: '12px',
        }}>
          <button type="button" onClick={volver} className="env-tap" aria-label="Volver"
            data-testid="back-button"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '7px',
              height: '38px', padding: '0 12px', borderRadius: '10px',
              border: `1px solid ${C.linea}`, background: C.lienzo,
              color: C.texto, fontSize: '14px', fontWeight: 600, cursor: 'pointer',
            }}>
            <ArrowLeft size={17} /> Volver
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: '15.5px', fontWeight: 700, color: C.tinta }}>
              Soporte
            </p>
            <p style={{ margin: 0, fontSize: '12px', color: C.tenue }}>Tus consultas</p>
          </div>
          <NotificationBell />
        </div>
      </header>

      <main style={{ maxWidth: '720px', margin: '0 auto', padding: '20px 16px 44px' }}>
        <div style={{
          ...tarjeta, padding: '16px 18px', marginBottom: '16px',
          display: 'flex', alignItems: 'center', gap: '13px',
        }}>
          <span style={{
            width: '40px', height: '40px', borderRadius: '12px', flexShrink: 0,
            background: C.marcaSuave, display: 'inline-flex',
            alignItems: 'center', justifyContent: 'center',
          }}>
            <LifeBuoy size={19} color={C.marca} />
          </span>
          <span>
            <span style={{ display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.tinta }}>
              Cada consulta lleva su propio número
            </span>
            <span style={{ ...ayuda, display: 'block', margin: '2px 0 0 0' }}>
              Así no se mezcla con las anteriores y podés seguirla hasta que se resuelva.
            </span>
          </span>
        </div>

        <div style={{
          ...tarjeta, overflow: 'hidden', display: 'flex', flexDirection: 'column',
          height: 'min(640px, calc(100vh - 260px))', minHeight: '420px',
        }}>
          <CasosDelCliente />
        </div>
      </main>
    </div>
  );
}
