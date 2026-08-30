/**
 * Chrome.jsx — El marco de las pantallas de envíos del usuario.
 *
 * Es el mismo encabezado que el resto de la app —volver, título, campana— para
 * que estas pantallas no parezcan de otro producto. Vive en un componente y no
 * copiado en cada página porque son cuatro pantallas de un mismo trámite: si el
 * botón de volver se mueve entre una y otra, el usuario deja de confiar en el
 * único control que siempre entiende.
 */
import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import NotificationBell from '../NotificationBell';
import { COLOR } from './estilos';

export default function Chrome({ titulo, volverA, ancho = '640px', accion, children }) {
  const navigate = useNavigate();
  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F7F8FB' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: '12px', padding: '14px 16px', backgroundColor: '#fff',
        borderBottom: `1px solid ${COLOR.borde}`, position: 'sticky', top: 0, zIndex: 10 }}>
        <button type="button" onClick={() => navigate(volverA || -1)}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', border: 'none',
            background: 'none', cursor: 'pointer', color: COLOR.suave, fontSize: '14px',
            fontWeight: 600, padding: 0 }}>
          <ArrowLeft size={18} /> Volver
        </button>
        <h1 style={{ fontSize: '17px', fontWeight: 700, color: COLOR.texto, margin: 0,
          textAlign: 'center', flex: 1 }}>
          {titulo}
        </h1>
        {accion || <NotificationBell />}
      </div>
      <div style={{ maxWidth: ancho, margin: '0 auto', padding: '20px 16px 48px 16px',
        display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {children}
      </div>
    </div>
  );
}
