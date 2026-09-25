import { useState, useEffect, Fragment } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { confirmar } from '../flujo/confirmar.js';
import { Landmark, Trash2, Plus, RefreshCw, Eye, EyeOff, CreditCard } from 'lucide-react';

// LA PANTALLA DE BANCOS
//
//   Los bancos de contabilidad son de donde salen los pagos de Retiros y a
//   donde entran las Recargas en bolívares. Hasta esta pantalla, crear o borrar
//   uno sólo se podía llamando a la API a mano: configurar exigía saber
//   programar. Las reglas —qué se puede borrar, qué nombre se puede repetir—
//   viven en el backend (`routes/accounting.py`); acá se muestra lo que dice.

const MONEDAS = {
  VES: { etiqueta: 'Bolívares', simbolo: 'Bs' },
  BRL: { etiqueta: 'Reales', simbolo: 'R$' },
};

function fmtSaldo(b) {
  const n = Number(b?.balance ?? 0);
  const texto = Number.isFinite(n)
    ? n.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : String(b?.balance ?? '—');
  return `${texto} ${MONEDAS[b?.currency]?.simbolo || b?.currency || ''}`;
}

function fmtFecha(d) {
  if (!d) return '—';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return String(d);
  return dt.toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric' });
}

// A QUE CUENTA LE DECIMOS AL CLIENTE QUE TRANSFIERA
//
//   Estos datos los ve el cliente en la recarga en bolívares y en el envío a
//   Brasil pagado en bolívares. Antes estaban escritos en el código de la
//   pantalla de recarga, que se le sirve a cualquier visitante. Las reglas
//   —20 dígitos que empiezan por el código del banco, un celular de 11— las
//   hace cumplir el servidor (`services/bancos.normalizar_cobro`): acá sólo
//   se escribe y se muestra lo que contesta.
function EditorDeCobro({ banco, onGuardado, estilos }) {
  const previo = banco.cobro || {};
  const [datos, setDatos] = useState({
    codigo: previo.codigo || '', titular: previo.titular || '', documento: previo.documento || '',
    numero_cuenta: previo.numero_cuenta || '', tipo_cuenta: previo.tipo_cuenta || 'Corriente',
    telefono: previo.telefono || '', publicado: !!previo.publicado,
  });
  const [guardando, setGuardando] = useState(false);
  const campo = (k) => (e) => setDatos({ ...datos, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });

  const guardar = async () => {
    setGuardando(true);
    try {
      const res = await api.put(`/admin/accounting/banks/${banco.bank_id}/cobro`, datos);
      toast.success(res.data?.message || 'Datos guardados');
      onGuardado();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudieron guardar los datos', { duration: 7000 });
    } finally {
      setGuardando(false);
    }
  };

  const { input, lbl } = estilos;
  const caja = (etiqueta, k, extra = {}) => (
    <div style={{ flex: extra.flex || '1 1 180px' }}>
      <label style={lbl}>{etiqueta}</label>
      <input value={datos[k]} onChange={campo(k)} placeholder={extra.placeholder || ''} inputMode={extra.inputMode}
        maxLength={extra.maxLength} style={{ ...input, width: '100%' }} data-testid={`cobro-${k}`} />
    </div>
  );

  return (
    <div style={{ padding: '14px 12px 16px', backgroundColor: 'var(--en-oscuro-superficie-2, #f9fafb)' }} data-testid="cobro-editor">
      <p style={{ fontSize: '13px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', margin: '0 0 4px 0' }}>
        Datos para que el cliente transfiera a «{banco.name}»
      </p>
      <p style={{ fontSize: '12px', color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '0 0 12px 0' }}>
        Revisalos dos veces: un dígito mal cargado manda la plata de un cliente a otra cuenta.
      </p>
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '10px' }}>
        {caja('Código del banco', 'codigo', { flex: '0 1 130px', placeholder: '0134', inputMode: 'numeric', maxLength: 4 })}
        {caja('Titular', 'titular', { flex: '2 1 240px', placeholder: 'Como figura en el banco' })}
        {caja('Cédula o RIF', 'documento', { placeholder: 'V-12345678' })}
      </div>
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: '12px' }}>
        {caja('Número de cuenta (transferencia)', 'numero_cuenta', { flex: '2 1 260px', placeholder: '20 dígitos', inputMode: 'numeric' })}
        <div>
          <label style={lbl}>Tipo de cuenta</label>
          <select value={datos.tipo_cuenta} onChange={campo('tipo_cuenta')} style={{ ...input, cursor: 'pointer' }} data-testid="cobro-tipo_cuenta">
            <option value="Corriente">Corriente</option>
            <option value="Ahorro">Ahorro</option>
          </select>
        </div>
        {caja('Teléfono de Pago Móvil', 'telefono', { placeholder: '04141234567', inputMode: 'tel' })}
      </div>
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', fontSize: '14px', color: 'var(--en-oscuro-texto, #111827)', cursor: 'pointer' }}>
          <input type="checkbox" checked={datos.publicado} onChange={campo('publicado')} data-testid="cobro-publicado" />
          Mostrárselo a los clientes para que transfieran acá
        </label>
        <button onClick={guardar} disabled={guardando} data-testid="cobro-guardar" style={{
          padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: 'var(--en-oscuro-acento, #2563eb)',
          color: '#fff', fontWeight: 700, fontSize: '14px', cursor: 'pointer', opacity: guardando ? 0.6 : 1,
        }}>{guardando ? 'Guardando…' : 'Guardar datos'}</button>
      </div>
    </div>
  );
}

export default function Bancos({ onCambio }) {
  const [bancos, setBancos] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [nombre, setNombre] = useState('');
  const [moneda, setMoneda] = useState('VES');
  const [saldo, setSaldo] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [abierto, setAbierto] = useState(null);

  const cargar = async () => {
    setCargando(true);
    try {
      const res = await api.get('/admin/accounting/banks');
      setBancos(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      toast.error('No se pudieron cargar los bancos');
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  // Retiros y Recargas tienen su propia copia de la lista, cargada al abrir el
  // panel. Sin avisarles, un banco recién creado no aparecería en ellas hasta
  // recargar la página.
  const cambio = () => { cargar(); if (onCambio) onCambio(); };

  const crear = async () => {
    const n = nombre.trim();
    if (n.length < 2) { toast.error('Escribí el nombre del banco'); return; }
    setGuardando(true);
    try {
      // El monto viaja como texto, como todo el dinero, y se escribe como
      // acá: «1.500,00». Con coma, la coma es el decimal y los puntos son de
      // miles. Cambiar sólo la coma mandaba «1.500.00», que el servidor
      // rechaza. Lo que no sea un número lo rechaza el servidor diciendo por qué.
      const limpio = saldo.trim().replace(/\s/g, '');
      const inicial = (limpio.includes(',') ? limpio.replace(/\./g, '').replace(',', '.') : limpio) || '0';
      await api.post('/admin/accounting/banks', { name: n, currency: moneda, initial_balance: inicial });
      toast.success(`Banco «${n}» creado`);
      setNombre('');
      setSaldo('');
      cambio();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo crear el banco');
    } finally {
      setGuardando(false);
    }
  };

  const borrar = async (b) => {
    if (!await confirmar({
      titulo: `¿Borrar el banco «${b.name}»?`,
      detalle: 'Sólo se puede borrar un banco que nunca se usó: sin movimientos, con saldo en cero y sin recargas esperando. Si tiene historia, te decimos cuál.',
      accion: 'Borrar banco',
      tono: 'peligro',
    })) return;
    try {
      await api.delete(`/admin/accounting/banks/${b.bank_id}`);
      toast.success(`Banco «${b.name}» borrado`);
      cambio();
    } catch (e) {
      // El 409 trae el motivo escrito para leerlo: movimientos, saldo o
      // recargas esperando. Se muestra entero y un rato más largo.
      toast.error(e?.response?.data?.detail || 'No se pudo borrar el banco', { duration: 7000 });
    }
  };

  const card = { backgroundColor: 'var(--en-oscuro-superficie, #fff)', borderRadius: '14px', padding: '16px', border: '1px solid var(--en-oscuro-linea, #eef0f4)' };
  const input = { padding: '11px 13px', borderRadius: '10px', border: '1px solid var(--en-oscuro-linea-fuerte, #d1d5db)', fontSize: '14px', outline: 'none', boxSizing: 'border-box', backgroundColor: 'var(--en-oscuro-superficie, #fff)', color: 'var(--en-oscuro-texto, #111827)' };
  const lbl = { display: 'block', fontSize: '12px', color: 'var(--en-oscuro-texto-2, #6b7280)', marginBottom: '6px' };
  const th = { textAlign: 'left', padding: '10px 12px', fontSize: '12px', fontWeight: 700, color: 'var(--en-oscuro-texto-2, #6b7280)', borderBottom: '1px solid var(--en-oscuro-linea, #eef0f4)' };
  const td = { padding: '12px', fontSize: '14px', color: 'var(--en-oscuro-texto, #111827)', borderBottom: '1px solid var(--en-oscuro-linea, #f3f4f6)' };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '16px' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Landmark size={20} style={{ color: 'var(--en-oscuro-acento, #2563eb)' }} /> Bancos
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '4px 0 0 0', maxWidth: '720px' }}>
            Las cuentas de donde salen los pagos de Retiros y a donde entran las Recargas en bolívares. Los saldos se mueven solos con cada operación; acá se cargan y se borran las cuentas.
          </p>
        </div>
        <button onClick={cargar} disabled={cargando} style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '9px 14px', borderRadius: '10px',
          border: '1px solid var(--en-oscuro-linea, #e5e7eb)', backgroundColor: 'var(--en-oscuro-superficie, #fff)', color: 'var(--en-oscuro-texto, #374151)', fontWeight: 600, fontSize: '14px', cursor: 'pointer',
        }}>
          <RefreshCw size={15} /> {cargando ? 'Cargando…' : 'Actualizar'}
        </button>
      </div>

      <div style={{ ...card, marginBottom: '16px' }}>
        <p style={{ fontSize: '13px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', margin: '0 0 12px 0' }}>Cargar un banco</p>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: '2 1 220px' }}>
            <label style={lbl}>Nombre</label>
            <input value={nombre} onChange={(e) => setNombre(e.target.value)} maxLength={60}
              placeholder="Ej: Banesco" style={{ ...input, width: '100%' }} data-testid="banco-nombre" />
          </div>
          <div>
            <label style={lbl}>Moneda</label>
            <select value={moneda} onChange={(e) => setMoneda(e.target.value)} style={{ ...input, cursor: 'pointer' }} data-testid="banco-moneda">
              <option value="VES">Bolívares (VES)</option>
              <option value="BRL">Reales (BRL)</option>
            </select>
          </div>
          <div style={{ flex: '1 1 160px' }}>
            <label style={lbl}>Saldo inicial</label>
            <input value={saldo} onChange={(e) => setSaldo(e.target.value)} inputMode="decimal"
              placeholder="0,00" style={{ ...input, width: '100%' }} data-testid="banco-saldo" />
          </div>
          <button onClick={crear} disabled={guardando} data-testid="banco-crear" style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '11px 18px', borderRadius: '10px',
            border: 'none', backgroundColor: 'var(--en-oscuro-acento, #2563eb)', color: '#fff', fontWeight: 700, fontSize: '14px', cursor: 'pointer', opacity: guardando ? 0.6 : 1,
          }}>
            <Plus size={16} /> {guardando ? 'Guardando…' : 'Cargar banco'}
          </button>
        </div>
        {moneda === 'VES' && (
          <p style={{ fontSize: '12px', color: 'var(--en-oscuro-texto-2, #6b7280)', margin: '10px 0 0 0' }}>
            Para que los clientes le transfieran, después de cargarlo tocá «Datos para el cliente» y publicalo.
          </p>
        )}
      </div>

      {!cargando && !bancos.some((b) => b.currency === 'VES' && b.cobro?.publicado) && (
        <div data-testid="bancos-sin-publicar" style={{ ...card, marginBottom: '16px', borderColor: 'var(--en-oscuro-alerta, #f59e0b)', backgroundColor: 'var(--en-oscuro-alerta-suave, #fffbeb)', color: 'var(--en-oscuro-texto, #92400e)', fontSize: '14px' }}>
          <strong>Ningún banco se les muestra a los clientes.</strong> Hasta que publiques uno, no pueden recargar en bolívares ni pagar en bolívares un envío a Brasil: no tienen a dónde transferir.
        </div>
      )}

      {cargando && bancos.length === 0 ? (
        <p style={{ color: 'var(--en-oscuro-texto-2, #6b7280)' }}>Cargando…</p>
      ) : bancos.length === 0 ? (
        <div style={{ ...card, textAlign: 'center', color: 'var(--en-oscuro-texto-2, #6b7280)' }}>
          Todavía no hay bancos cargados. Sin ellos no se pueden aprobar recargas en bolívares.
        </div>
      ) : (
        <div style={{ ...card, padding: 0, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={th}>Banco</th>
                <th style={th}>Moneda</th>
                <th style={{ ...th, textAlign: 'right' }}>Saldo</th>
                <th style={th}>Cargado</th>
                <th style={th} />
              </tr>
            </thead>
            <tbody>
              {bancos.map((b) => (
                <Fragment key={b.bank_id}>
                <tr data-testid="banco-fila">
                  <td style={td}>
                    <span style={{ fontWeight: 600 }}>{b.name}</span>
                    {b.is_gateway && (
                      <span style={{ marginLeft: '8px', padding: '2px 8px', borderRadius: '999px', fontSize: '11px', fontWeight: 700, backgroundColor: 'var(--en-oscuro-acento-suave, #eff6ff)', color: 'var(--en-oscuro-acento, #2563eb)' }}>
                        Pasarela
                      </span>
                    )}
                    {b.currency === 'VES' && !b.is_gateway && (
                      <span data-testid="banco-visible" style={{ marginLeft: '8px', display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '999px', fontSize: '11px', fontWeight: 700,
                        backgroundColor: b.cobro?.publicado ? 'var(--en-oscuro-exito-suave, #ecfdf5)' : 'var(--en-oscuro-superficie-2, #f3f4f6)',
                        color: b.cobro?.publicado ? 'var(--en-oscuro-exito, #047857)' : 'var(--en-oscuro-texto-2, #6b7280)' }}>
                        {b.cobro?.publicado ? <><Eye size={12} /> Lo ven los clientes</> : <><EyeOff size={12} /> No lo ven los clientes</>}
                      </span>
                    )}
                  </td>
                  <td style={td}>{MONEDAS[b.currency]?.etiqueta || b.currency}</td>
                  <td style={{ ...td, textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{fmtSaldo(b)}</td>
                  <td style={{ ...td, color: 'var(--en-oscuro-texto-2, #6b7280)' }}>{fmtFecha(b.created_at)}</td>
                  <td style={{ ...td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {b.currency === 'VES' && !b.is_gateway && (
                      <button onClick={() => setAbierto(abierto === b.bank_id ? null : b.bank_id)} data-testid="banco-cobro" style={{
                        display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '6px 10px', borderRadius: '8px', marginRight: '8px',
                        border: '1px solid var(--en-oscuro-linea, #e5e7eb)', backgroundColor: 'var(--en-oscuro-superficie, #fff)', color: 'var(--en-oscuro-texto, #374151)', fontWeight: 600, fontSize: '13px', cursor: 'pointer',
                      }}>
                        <CreditCard size={14} /> Datos para el cliente
                      </button>
                    )}
                    {/* La cuenta de una pasarela la crea la aplicación y la
                        vuelve a necesitar con el próximo cobro: no se ofrece
                        borrarla. El backend lo frena igual. */}
                    {!b.is_gateway && (
                      <button onClick={() => borrar(b)} data-testid="banco-borrar" style={{
                        display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '6px 10px', borderRadius: '8px',
                        border: '1px solid var(--en-oscuro-error-suave, #fecaca)', backgroundColor: 'var(--en-oscuro-superficie, #fff)', color: 'var(--en-oscuro-error, #dc2626)', fontWeight: 600, fontSize: '13px', cursor: 'pointer',
                      }}>
                        <Trash2 size={14} /> Borrar
                      </button>
                    )}
                  </td>
                </tr>
                {abierto === b.bank_id && (
                  <tr>
                    <td colSpan={5} style={{ padding: 0, borderBottom: '1px solid var(--en-oscuro-linea, #f3f4f6)' }}>
                      <EditorDeCobro banco={b} estilos={{ input, lbl }} onGuardado={() => { setAbierto(null); cambio(); }} />
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
