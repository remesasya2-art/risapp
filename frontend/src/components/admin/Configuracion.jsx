/**
 * components/admin/Configuracion.jsx — Los números del panel, sin tocar código.
 *
 * ESTA PANTALLA NO SABE QUE AJUSTES EXISTEN
 *
 *   Los pide a `GET /admin/configuracion` y dibuja lo que venga: cada ajuste
 *   trae su etiqueta, su ayuda, su unidad, su rango y su valor de fábrica.
 *
 *   Eso es todo el punto. Agregar el mínimo de PIX o el cupo sin verificación
 *   es una entrada en `services/configuracion.AJUSTES` y aparece acá sola, sin
 *   tocar este archivo y sin volver a desplegar el frontend.
 *
 *   Lo contrario es `BtcAdminConfig.jsx`, que tiene un `useState` por número y
 *   repite en JavaScript la validación que el servidor ya hace. Dos copias de
 *   la misma regla, y la de JavaScript es la que se olvida de actualizar.
 *
 * LA VALIDACION LA HACE EL SERVIDOR, Y SE MUESTRA LO QUE DIGA
 *
 *   Acá sólo se avisa lo obvio antes de mandar —que el campo no esté vacío— y
 *   el resto lo decide `services/configuracion.normalizar`, que es el que
 *   conoce los rangos y el que devuelve el motivo escrito. Repetir los rangos
 *   en el navegador sería tener dos verdades y creerle a la equivocada.
 *
 * LA PLATA VIAJA COMO TEXTO
 *
 *   El campo es `type="text"` y no `type="number"`, y lo que se manda es la
 *   cadena tal cual. Dos motivos: un `15.1` metido en un JSON ya perdió
 *   precisión antes de que el servidor lo lea, y `type="number"` no deja
 *   escribir la coma decimal, que es como se escribe un monto en Brasil.
 *   El servidor acepta «15,50» y «15.50» por igual.
 */
import { useEffect, useState } from 'react';
import { Save, RefreshCw, RotateCcw, SlidersHorizontal } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';

export default function Configuracion() {
  const [ajustes, setAjustes] = useState(null);
  const [escrito, setEscrito] = useState({});
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);

  const cargar = async () => {
    setCargando(true);
    try {
      const r = await api.get('/admin/configuracion');
      setAjustes(r.data.ajustes || []);
      // Lo escrito arranca igual a lo guardado, así que «cambió algo» se
      // puede comparar campo por campo sin guardar una segunda copia.
      const inicial = {};
      (r.data.ajustes || []).forEach((a) => { inicial[a.clave] = String(a.valor); });
      setEscrito(inicial);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo leer la configuración');
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const hayCambios = (ajustes || []).some(
    (a) => String(escrito[a.clave] ?? '') !== String(a.valor));

  const guardar = async () => {
    const vacio = (ajustes || []).find((a) => !String(escrito[a.clave] ?? '').trim());
    if (vacio) return toast.error(`«${vacio.etiqueta}» quedó vacío.`);

    // Sólo lo que cambió. Mandar los tres siempre haría que el libro de
    // auditoría no distinga «puse el bono en 20» de «abrí la pantalla y
    // guardé sin tocar nada».
    const valores = {};
    ajustes.forEach((a) => {
      if (String(escrito[a.clave]) !== String(a.valor)) valores[a.clave] = escrito[a.clave];
    });
    if (!Object.keys(valores).length) return toast('No cambiaste nada.');

    setGuardando(true);
    try {
      const r = await api.put('/admin/configuracion', { valores });
      setAjustes(r.data.ajustes || []);
      const nuevo = {};
      (r.data.ajustes || []).forEach((a) => { nuevo[a.clave] = String(a.valor); });
      setEscrito(nuevo);
      toast.success(r.data.cambiados?.length
        ? `Guardado (${r.data.cambiados.length})`
        : 'No hubo cambios');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'No se pudo guardar');
    } finally {
      setGuardando(false);
    }
  };

  const volverAFabrica = () => {
    const inicial = {};
    ajustes.forEach((a) => { inicial[a.clave] = String(a.defecto); });
    setEscrito(inicial);
    toast('Valores de fábrica puestos en los campos. Todavía no se guardaron.');
  };

  if (cargando) {
    return (
      <div style={{ padding: '48px', textAlign: 'center' }}>
        <RefreshCw size={26} style={{ color: '#6366f1', animation: 'spin 1s linear infinite' }} />
      </div>
    );
  }

  if (!ajustes?.length) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: '#6b7280' }}>
        No hay ajustes configurables todavía.
      </div>
    );
  }

  const tarjeta = {
    backgroundColor: '#ffffff', borderRadius: '16px', padding: '24px',
    border: '1px solid #e5e7eb',
  };

  return (
    <div data-testid="config-general" style={{ maxWidth: '760px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '18px' }}>
        <span style={{
          width: '40px', height: '40px', borderRadius: '12px', flexShrink: 0,
          background: '#eef2ff', display: 'inline-flex',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <SlidersHorizontal size={19} color="#4f46e5" />
        </span>
        <div>
          <h2 style={{ margin: 0, fontSize: '19px', fontWeight: 700, color: '#111827' }}>
            Configuración
          </h2>
          <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#6b7280' }}>
            Cambiar estos números no requiere desplegar nada. Queda anotado en Auditoría.
          </p>
        </div>
      </div>

      <div style={tarjeta}>
        {ajustes.map((a, i) => (
          <div key={a.clave}
            data-testid={`ajuste-${a.clave}`}
            style={{
              paddingTop: i === 0 ? 0 : '20px',
              marginTop: i === 0 ? 0 : '20px',
              borderTop: i === 0 ? 'none' : '1px solid #f3f4f6',
            }}>
            <label htmlFor={`aj-${a.clave}`} style={{
              display: 'block', fontSize: '14px', fontWeight: 600, color: '#111827',
            }}>
              {a.etiqueta}
            </label>
            <p style={{ margin: '4px 0 10px', fontSize: '12.5px', color: '#6b7280', lineHeight: 1.5 }}>
              {a.ayuda}
            </p>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <input
                id={`aj-${a.clave}`}
                data-testid={`campo-${a.clave}`}
                type="text"
                inputMode="decimal"
                value={escrito[a.clave] ?? ''}
                onChange={(e) => setEscrito({ ...escrito, [a.clave]: e.target.value })}
                style={{
                  width: '160px', height: '44px', padding: '0 12px',
                  borderRadius: '10px', border: '1px solid #d1d5db',
                  fontSize: '15px', fontWeight: 600, color: '#111827',
                  fontVariantNumeric: 'tabular-nums',
                }}
              />
              {a.unidad ? (
                <span style={{ fontSize: '14px', color: '#6b7280' }}>{a.unidad}</span>
              ) : null}
              <span style={{ fontSize: '12px', color: '#9ca3af', marginLeft: 'auto' }}>
                entre {a.minimo} y {a.maximo} · de fábrica {a.defecto}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', gap: '10px', marginTop: '18px', flexWrap: 'wrap' }}>
        <button type="button" onClick={guardar} disabled={guardando || !hayCambios}
          data-testid="guardar-config"
          style={{
            height: '46px', padding: '0 20px', borderRadius: '11px', border: 'none',
            background: hayCambios ? '#4f46e5' : '#c7d2fe', color: '#fff',
            fontSize: '14.5px', fontWeight: 600,
            cursor: guardando || !hayCambios ? 'not-allowed' : 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: '8px',
          }}>
          <Save size={17} />
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>

        <button type="button" onClick={volverAFabrica} disabled={guardando}
          data-testid="fabrica-config"
          style={{
            height: '46px', padding: '0 18px', borderRadius: '11px',
            border: '1px solid #d1d5db', background: '#fff', color: '#374151',
            fontSize: '14.5px', fontWeight: 600, cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: '8px',
          }}>
          <RotateCcw size={16} />
          Valores de fábrica
        </button>
      </div>
    </div>
  );
}
