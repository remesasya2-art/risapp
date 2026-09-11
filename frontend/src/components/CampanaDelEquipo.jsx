import { useState, useEffect, useRef, useCallback } from 'react';
import { Bell, CheckCheck } from 'lucide-react';
import api from '../utils/api';

/**
 * La campana del PANEL DE CONTROL: lo que el equipo tiene que atender.
 *
 * POR QUE NO ES LA MISMA QUE LA DEL CLIENTE
 *
 *   Son dos bandejas. `NotificationBell` muestra lo que le pasa a esa persona;
 *   ésta muestra lo que hay que resolver: un KYC nuevo, una orden de Bitcoin
 *   pagada, la tasa vencida. El servidor las separa por el campo `ambito`.
 *
 *   Hasta ahora esta campana no existía en el panel. Un operador trabajando
 *   acá adentro no tenía forma de enterarse de nada: tenía que salirse a una
 *   pantalla de cliente para mirar.
 *
 * POR QUE SE DESPLIEGA Y NO NAVEGA
 *
 *   Quien la toca está a mitad de una orden. Mandarlo a otra página le hace
 *   perder el lugar, y volver cuesta encontrar de nuevo dónde estaba. El
 *   desplegable se abre encima y se cierra donde estaba.
 *
 * Y AL TOCAR UN AVISO, SALTA A DONDE SE RESUELVE
 *
 *   Un aviso que dice «hay un KYC nuevo» y te deja buscándolo a mano es media
 *   ayuda. Ver `SECCION_DE`.
 */

// A qué pestaña del panel lleva cada clase de aviso. Lo que no está acá no
// salta a ningún lado: se lee y ya. Es a propósito —un salto a la pestaña
// equivocada es peor que ninguno—.
const SECCION_DE = (aviso) => {
  const datos = aviso?.data || {};
  switch (aviso?.type) {
    case 'kyc':
      return 'kyc';
    case 'btc_remesa_pagada':
      return 'btc';
    case 'warning':
      // Las dos alertas que existen hoy con este tipo se distinguen por lo que
      // traen: la de la tasa dice su motivo, la del pago tardío trae la orden.
      if (datos.motivo === 'tasa_usd_ves_btc_vencida') return 'rates';
      if (datos.remesa_id) return 'btc';
      return null;
    default:
      return null;
  }
};

const CADA = 30000;   // Lo mismo que la campana del cliente.

function cuandoFue(iso) {
  if (!iso) return '';
  const cuando = new Date(iso);
  const minutos = Math.floor((Date.now() - cuando) / 60000);
  if (minutos < 1) return 'Ahora';
  if (minutos < 60) return `Hace ${minutos} min`;
  const horas = Math.floor(minutos / 60);
  if (horas < 24) return `Hace ${horas}h`;
  const dias = Math.floor(horas / 24);
  if (dias < 7) return `Hace ${dias}d`;
  return cuando.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
}

export default function CampanaDelEquipo({ onIrA }) {
  const [avisos, setAvisos] = useState([]);
  const [sinLeer, setSinLeer] = useState(0);
  const [abierta, setAbierta] = useState(false);
  const caja = useRef(null);

  const contar = useCallback(async () => {
    try {
      const r = await api.get('/notifications/unread-count', { params: { ambito: 'trabajo' } });
      setSinLeer(r.data?.unread_count || 0);
    } catch {
      // Que no se pueda contar no puede llenar la consola del operador de
      // errores cada treinta segundos. El número se queda como estaba.
    }
  }, []);

  const traer = useCallback(async () => {
    try {
      const r = await api.get('/notifications', { params: { ambito: 'trabajo' } });
      setAvisos(Array.isArray(r.data) ? r.data : []);
    } catch {
      setAvisos([]);
    }
  }, []);

  useEffect(() => {
    contar();
    const reloj = setInterval(contar, CADA);
    return () => clearInterval(reloj);
  }, [contar]);

  // Cerrar al tocar afuera o con Escape. Sin esto el desplegable se queda
  // abierto tapando la pestaña a la que acabás de saltar.
  useEffect(() => {
    if (!abierta) return undefined;
    const afuera = (e) => { if (caja.current && !caja.current.contains(e.target)) setAbierta(false); };
    const escape = (e) => { if (e.key === 'Escape') setAbierta(false); };
    document.addEventListener('mousedown', afuera);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', afuera);
      document.removeEventListener('keydown', escape);
    };
  }, [abierta]);

  const alternar = async () => {
    const abriendo = !abierta;
    setAbierta(abriendo);
    if (abriendo) await traer();
  };

  const abrirAviso = async (aviso) => {
    // Primero se marca leído en la pantalla y después se avisa al servidor: si
    // la red tarda, el operador ya saltó a la sección y el aviso no quedó
    // parpadeando como nuevo.
    if (!aviso.read) {
      setAvisos((previos) => previos.map((a) =>
        a.notification_id === aviso.notification_id ? { ...a, read: true } : a));
      setSinLeer((n) => Math.max(0, n - 1));
      try {
        await api.post(`/notifications/${aviso.notification_id}/read`);
      } catch {
        contar();   // No se pudo: que el número vuelva a la verdad del servidor.
      }
    }
    const seccion = SECCION_DE(aviso);
    if (seccion && onIrA) {
      setAbierta(false);
      onIrA(seccion);
    }
  };

  const marcarTodas = async () => {
    try {
      await api.post('/notifications/mark-all-read', null, { params: { ambito: 'trabajo' } });
      setAvisos((previos) => previos.map((a) => ({ ...a, read: true })));
      setSinLeer(0);
    } catch {
      contar();
    }
  };

  return (
    <div ref={caja} style={{ position: 'relative' }}>
      <button
        onClick={alternar}
        style={{
          position: 'relative', width: '40px', height: '40px', borderRadius: '12px',
          backgroundColor: abierta ? '#e0e7ff' : '#f3f4f6', border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
        data-testid="campana-del-equipo"
        title="Avisos del equipo"
      >
        <Bell style={{ width: '20px', height: '20px', color: abierta ? '#4338ca' : '#374151' }} />
        {sinLeer > 0 && (
          <span
            style={{
              position: 'absolute', top: '4px', right: '4px', minWidth: '18px', height: '18px',
              borderRadius: '9999px', backgroundColor: '#ef4444', color: '#ffffff',
              fontSize: '11px', fontWeight: '700', display: 'flex', alignItems: 'center',
              justifyContent: 'center', padding: '0 4px', border: '2px solid #ffffff',
            }}
            data-testid="campana-del-equipo-contador"
          >
            {sinLeer > 99 ? '99+' : sinLeer}
          </span>
        )}
      </button>

      {abierta && (
        <div
          style={{
            position: 'absolute', top: '48px', right: 0, width: '360px', maxWidth: 'calc(100vw - 32px)',
            maxHeight: '420px', overflowY: 'auto', backgroundColor: '#ffffff',
            borderRadius: '14px', border: '1px solid #e5e7eb',
            boxShadow: '0 12px 32px rgba(0,0,0,0.14)', zIndex: 60,
          }}
          data-testid="campana-del-equipo-panel"
        >
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '12px 14px', borderBottom: '1px solid #f1f2f6', position: 'sticky',
            top: 0, backgroundColor: '#ffffff',
          }}>
            <strong style={{ fontSize: '14px', color: '#111827' }}>Avisos del equipo</strong>
            {avisos.some((a) => !a.read) && (
              <button
                onClick={marcarTodas}
                style={{
                  display: 'flex', alignItems: 'center', gap: '6px', border: 'none',
                  background: 'transparent', color: '#4338ca', fontSize: '12px',
                  fontWeight: 600, cursor: 'pointer', padding: 0,
                }}
                data-testid="campana-del-equipo-marcar-todas"
              >
                <CheckCheck style={{ width: '14px', height: '14px' }} /> Marcar todas
              </button>
            )}
          </div>

          {avisos.length === 0 ? (
            <p style={{ padding: '28px 14px', textAlign: 'center', color: '#9ca3af', fontSize: '13px', margin: 0 }}>
              No hay nada pendiente del equipo.
            </p>
          ) : (
            avisos.map((aviso) => {
              const saltaA = SECCION_DE(aviso);
              return (
                <button
                  key={aviso.notification_id}
                  onClick={() => abrirAviso(aviso)}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left', border: 'none',
                    borderBottom: '1px solid #f6f7f9', padding: '12px 14px',
                    backgroundColor: aviso.read ? '#ffffff' : '#f5f3ff',
                    cursor: saltaA ? 'pointer' : 'default',
                  }}
                  data-testid={`campana-del-equipo-aviso-${aviso.notification_id}`}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px' }}>
                    <span style={{ fontSize: '13px', fontWeight: aviso.read ? 500 : 700, color: '#111827' }}>
                      {aviso.title}
                    </span>
                    <span style={{ fontSize: '11px', color: '#9ca3af', whiteSpace: 'nowrap' }}>
                      {cuandoFue(aviso.created_at)}
                    </span>
                  </div>
                  <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#4b5563', whiteSpace: 'pre-line' }}>
                    {aviso.message}
                  </p>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
