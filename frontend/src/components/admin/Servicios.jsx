/**
 * components/admin/Servicios.jsx — Prender y apagar cada servicio de RIS.
 *
 * RIS son tres servicios que se prenden por separado —remesas, encomiendas y
 * el banco— sobre una plataforma común que no se apaga. Esta pantalla los
 * muestra juntos, con el nombre de cada estado y lo que pasa en él, para que
 * apagar remesas el día que el banco lo necesite sea un botón y no buscar
 * «remesas_abiertas = 0» entre treinta números de Configuración.
 *
 * NO ES OTRA PUERTA
 *
 *   Lee de `GET /admin/servicios` y guarda por `PUT /admin/configuracion`, la
 *   misma ruta de la pantalla de Configuración. Así cada cambio pasa por la
 *   validación, los seguros entre ajustes, los cuatro ojos del núcleo y el
 *   libro de auditoría de siempre. Si el servidor dice que no, se muestra lo
 *   que diga: esta pantalla no repite ninguna regla.
 */
import { useEffect, useState } from 'react';
import { Power, RefreshCw, Send, Boxes, Landmark } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { confirmar } from '../flujo/confirmar.js';

const ICONO = { remesas: Send, encomiendas: Boxes, banco: Landmark };

export default function Servicios({ onCambio }) {
  const [servicios, setServicios] = useState(null);
  const [guardando, setGuardando] = useState(null);

  const cargar = () => api.get('/admin/servicios')
    .then((r) => setServicios(r.data?.servicios || []))
    .catch((err) => {
      toast.error(err?.response?.data?.detail || 'No se pudo leer el estado de los servicios');
      setServicios([]);
    });

  useEffect(() => { cargar(); }, []);

  const cambiar = async (servicio, estado) => {
    if (estado.valor === servicio.valor) return;
    if (!await confirmar({
      titulo: `¿Pasar ${servicio.nombre} a «${estado.nombre}»?`,
      detalle: estado.detalle,
      accion: `Sí, pasar a ${estado.nombre.toLowerCase()}`,
    })) return;
    setGuardando(servicio.servicio);
    try {
      await api.put('/admin/configuracion', { valores: { [servicio.llave]: String(estado.valor) } });
      toast.success(`${servicio.nombre}: ${estado.nombre}`);
      await cargar();
      if (onCambio) onCambio();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo cambiar');
    } finally {
      setGuardando(null);
    }
  };

  const tarjeta = {
    backgroundColor: 'var(--en-oscuro-superficie, #ffffff)',
    border: '1px solid var(--en-oscuro-linea, #e5e7eb)', borderRadius: '16px', padding: '20px',
  };

  return (
    <div data-testid="servicios" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: 0, fontSize: '20px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)' }}>
            <Power style={{ width: '20px', height: '20px' }} /> Servicios
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '13.5px', color: 'var(--en-oscuro-texto-2, #6b7280)' }}>
            Cada servicio se prende y se apaga por separado. La plataforma —personal,
            auditoría, respaldo, configuración— queda siempre prendida.
          </p>
        </div>
        <button onClick={cargar} title="Actualizar" style={{ width: '40px', height: '40px', borderRadius: '12px', border: 'none', cursor: 'pointer', backgroundColor: 'var(--en-oscuro-superficie-2, #f3f4f6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <RefreshCw style={{ width: '18px', height: '18px', color: 'var(--en-oscuro-texto, #374151)' }} />
        </button>
      </div>

      {servicios === null && <p style={{ color: 'var(--en-oscuro-texto-2, #6b7280)' }}>Cargando…</p>}

      {(servicios || []).map((s) => {
        const Icono = ICONO[s.servicio] || Power;
        const actual = s.estados.find((e) => e.valor === s.valor);
        return (
          <div key={s.servicio} style={tarjeta} data-testid={`servicio-${s.servicio}`}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '12px', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'var(--en-oscuro-acento-suave, #eef2ff)' }}>
                <Icono style={{ width: '20px', height: '20px', color: 'var(--en-oscuro-acento, #4338ca)' }} />
              </div>
              <div style={{ flex: 1, minWidth: '200px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <strong style={{ fontSize: '16px', color: 'var(--en-oscuro-texto, #111827)' }}>{s.nombre}</strong>
                  <span data-testid={`estado-${s.servicio}`} style={{
                    fontSize: '12px', fontWeight: 700, padding: '2px 10px', borderRadius: '9999px',
                    backgroundColor: s.encendido ? 'var(--en-oscuro-exito-suave, #dcfce7)' : 'var(--en-oscuro-superficie-3, #e5e7eb)',
                    color: s.encendido ? 'var(--en-oscuro-exito, #166534)' : 'var(--en-oscuro-texto-2, #4b5563)',
                  }}>{s.estado}</span>
                </div>
                <p style={{ margin: '4px 0 0 0', fontSize: '13.5px', color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{s.descripcion}</p>
                {actual && <p style={{ margin: '8px 0 0 0', fontSize: '13px', color: 'var(--en-oscuro-texto, #374151)' }}>{actual.detalle}</p>}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', marginTop: '14px', flexWrap: 'wrap' }}>
              {s.estados.map((e) => {
                const elegido = e.valor === s.valor;
                return (
                  <button key={e.valor} onClick={() => cambiar(s, e)}
                    disabled={guardando !== null}
                    data-testid={`poner-${s.servicio}-${e.valor}`}
                    style={{
                      padding: '8px 14px', borderRadius: '10px', fontSize: '13.5px', fontWeight: 600,
                      cursor: elegido ? 'default' : 'pointer',
                      border: elegido ? '1.5px solid var(--en-oscuro-acento, #4f46e5)' : '1px solid var(--en-oscuro-linea, #d1d5db)',
                      backgroundColor: elegido ? 'var(--en-oscuro-acento-suave, #eef2ff)' : 'transparent',
                      color: elegido ? 'var(--en-oscuro-acento, #4338ca)' : 'var(--en-oscuro-texto, #374151)',
                    }}>
                    {e.nombre}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
