/**
 * Seguimiento.jsx — La página pública de seguimiento.
 *
 * NO PIDE SESION, Y NO MUESTRA UN SOLO DATO PERSONAL
 *   Es un link que el usuario le manda a quien espera la caja. Del otro lado
 *   puede haber cualquiera, así que lo único que se ve es en qué estado está el
 *   paquete, a qué ciudad va, y la guía del transportista cuando ya se entregó.
 *   Ni el nombre de quien recibe, ni el documento, ni el teléfono, ni el precio.
 *   La proyección del backend es una lista blanca por la misma razón.
 *
 * UN TOKEN QUE NO EXISTE Y UNO MAL ESCRITO SE CONTESTAN IGUAL
 *   Distinguirlos convertiría esta página en un oráculo para adivinar tokens. El
 *   backend devuelve lo mismo para los dos casos, y acá se muestra un solo
 *   mensaje.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { PackageSearch, RefreshCw } from 'lucide-react';
import api from '../utils/api';
import { Boton, Cargando, Vacio } from '../components/envios/ui';
import { COLOR, bajada, tarjeta, titulo } from '../components/envios/estilos';
import { tonoDe } from '../components/envios/estados';

const fecha = (v) => (v ? new Date(v).toLocaleString('es-AR',
  { dateStyle: 'short', timeStyle: 'short' }) : '');

export default function Seguimiento() {
  const { token } = useParams();
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [falla, setFalla] = useState(null);
  const peticion = useRef(0);

  const cargar = useCallback(async () => {
    const mia = ++peticion.current;
    try {
      const res = await api.get(`/envios/seguimiento/${token}`);
      if (mia !== peticion.current) return;
      setDatos(res.data);
      setFalla(null);
    } catch (err) {
      if (mia !== peticion.current) return;
      // 404 y token mal escrito son la misma respuesta a propósito. Un 5xx sí es
      // otra cosa: ahí el paquete existe y somos nosotros los que fallamos.
      setFalla(err?.response?.status >= 500 ? 'servidor' : 'sin_envio');
    } finally {
      if (mia === peticion.current) setCargando(false);
    }
  }, [token]);

  useEffect(() => {
    (async () => { await cargar(); })();
    return () => { peticion.current += 1; };
  }, [cargar]);

  const tono = tonoDe(datos?.estado);

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#F7F8FB' }}>
      <div style={{ padding: '18px 16px', backgroundColor: '#fff',
        borderBottom: `1px solid ${COLOR.borde}`, textAlign: 'center' }}>
        <h1 style={{ fontSize: '17px', fontWeight: 700, color: COLOR.texto, margin: 0,
          display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
          <PackageSearch size={18} /> Seguimiento
        </h1>
      </div>

      <div style={{ maxWidth: '560px', margin: '0 auto', padding: '20px 16px 48px 16px',
        display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {cargando && !datos ? <Cargando texto="Buscando el paquete…" /> : null}

        {falla === 'sin_envio' ? (
          <Vacio titulo="No encontramos ese paquete">
            Revisá que el link esté completo. Si lo copiaste a mano, puede haberse cortado.
          </Vacio>
        ) : null}
        {falla === 'servidor' ? (
          <Vacio titulo="No pudimos consultar ahora">
            El paquete está: lo que falló es la consulta. Probá de nuevo en un minuto.
            <div><Boton variante="secundario" style={{ marginTop: '12px' }}
              onClick={() => { setCargando(true); cargar(); }}>
              <RefreshCw size={14} /> Reintentar
            </Boton></div>
          </Vacio>
        ) : null}

        {datos ? (
          <>
            <div style={{ ...tarjeta, backgroundColor: tono.fondo, borderColor: tono.borde }}>
              <p style={{ margin: 0, fontSize: '12px', fontWeight: 700, letterSpacing: '0.04em',
                textTransform: 'uppercase', color: tono.texto, opacity: 0.8,
                fontFamily: 'monospace' }}>
                {datos.display_id}
              </p>
              <p style={{ margin: '6px 0 0 0', fontSize: '24px', fontWeight: 800,
                color: tono.texto }}>
                {datos.estado_titulo}
              </p>
              {datos.estado_detalle ? (
                <p style={{ margin: '6px 0 0 0', fontSize: '14px', color: tono.texto,
                  lineHeight: 1.5 }}>{datos.estado_detalle}</p>
              ) : null}
            </div>

            <div style={tarjeta}>
              <h3 style={titulo}>A dónde va</h3>
              <p style={{ ...bajada, margin: 0 }}>
                {datos.destino?.ciudad || '—'}
                {datos.destino?.estado ? `, ${datos.destino.estado}` : ''}
              </p>
              {datos.guia_transportista ? (
                <p style={{ margin: '10px 0 0 0', fontSize: '14px', color: COLOR.texto }}>
                  Guía del transportista:{' '}
                  <strong style={{ fontFamily: 'monospace' }}>{datos.guia_transportista}</strong>
                </p>
              ) : null}
            </div>

            {datos.timeline?.length ? (
              <div style={tarjeta}>
                <h3 style={titulo}>Por dónde pasó</h3>
                {datos.timeline.map((t, i) => (
                  <div key={i} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start',
                    padding: '8px 0' }}>
                    <div style={{ width: '10px', height: '10px', borderRadius: '50%',
                      backgroundColor: i === datos.timeline.length - 1
                        ? COLOR.primario : COLOR.borde,
                      marginTop: '5px', flexShrink: 0 }} />
                    <div>
                      <p style={{ margin: 0, fontSize: '14px', fontWeight: 600,
                        color: COLOR.texto }}>
                        {t.titulo || t.estado}
                      </p>
                      <p style={{ margin: 0, fontSize: '12px', color: COLOR.suave }}>
                        {fecha(t.at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            <Boton variante="secundario" onClick={() => { setCargando(true); cargar(); }}
              cargando={cargando} style={{ alignSelf: 'center' }}>
              <RefreshCw size={14} /> Actualizar
            </Boton>
          </>
        ) : null}
      </div>
    </div>
  );
}
