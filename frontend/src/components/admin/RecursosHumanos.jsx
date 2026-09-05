/**
 * RecursosHumanos.jsx — El legajo del personal y la única puerta de alta.
 *
 * POR QUE ESTA PANTALLA EXISTE
 *
 *   Antes el personal se creaba desde la pantalla de usuarios, y esa ruta
 *   promovía a `admin` cualquier cuenta existente sin dejar rastro. Acá el
 *   alta es explícita, deja legajo y deja línea en el libro de auditoría.
 *
 *   Sólo la ve el super administrador. El alta de personal no es un permiso
 *   que se delega, así que el backend la protege con `get_super_admin` y el
 *   panel ni siquiera muestra la pestaña.
 *
 * LO QUE HAY QUE ENTENDER AL USARLA
 *
 *   Una cuenta de personal NO puede hacer transacciones a título personal.
 *   Por eso no se puede dar de alta a alguien que tenga saldo: quedaría
 *   encerrado. El backend lo rechaza y acá se muestra el motivo tal cual.
 */
import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../../utils/api';
import { confirmar, pedirTexto } from '../flujo/confirmar.js';
import {
  RefreshCw, UserPlus, Users, ShieldCheck, X, Trash2, History, Save,
  Mail, AlertTriangle,
} from 'lucide-react';

function fmtFecha(d) {
  if (!d) return '—';
  const dt = new Date(d);
  if (isNaN(dt.getTime())) return String(d);
  return dt.toLocaleString('es-VE', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

const VACIO = {
  email: '', nombre_completo: '', cargo: '', area: '',
  documento: '', telefono: '', fecha_ingreso: '', notas: '', permisos: [],
};

export default function RecursosHumanos() {
  const [personal, setPersonal] = useState([]);
  const [permisos, setPermisos] = useState({});
  const [cargando, setCargando] = useState(true);
  const [incluirBajas, setIncluirBajas] = useState(false);
  const [alta, setAlta] = useState(null);        // el formulario, o null
  const [guardando, setGuardando] = useState(false);
  const [detalle, setDetalle] = useState(null);  // {ficha, historial}
  const [editandoPermisos, setEditandoPermisos] = useState(null);

  // Sólo trae los datos: no toca el estado. Así el efecto puede usarla sin
  // llamar a setState de forma sincrónica —que dispara renders en cascada— y
  // el botón de Actualizar puede prender el spinner por su cuenta.
  const traer = async (conBajas) => {
    const [lista, cat] = await Promise.all([
      api.get(`/admin/rrhh?incluir_bajas=${conBajas}`),
      api.get('/admin/rrhh/permisos'),
    ]);
    return { personal: lista.data?.personal || [], permisos: cat.data?.permisos || {} };
  };

  const cargar = async () => {
    setCargando(true);
    try {
      const r = await traer(incluirBajas);
      setPersonal(r.personal);
      setPermisos(r.permisos);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo cargar el personal');
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    // `vigente` descarta la respuesta de una petición que ya no interesa. Sin
    // esto, tildar y destildar "Ver bajas" rápido puede dejar en pantalla la
    // respuesta de la primera, que llega después. Es el mismo error que tenía
    // el Libro Mayor y dejaba la página en blanco.
    let vigente = true;
    traer(incluirBajas)
      .then((r) => {
        if (!vigente) return;
        setPersonal(r.personal);
        setPermisos(r.permisos);
      })
      .catch((e) => {
        if (vigente) toast.error(e?.response?.data?.detail || 'No se pudo cargar el personal');
      })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [incluirBajas]);

  const darDeAlta = async () => {
    if (!alta.email || !alta.nombre_completo || !alta.cargo || !alta.area) {
      toast.error('Correo, nombre, cargo y área son obligatorios');
      return;
    }
    setGuardando(true);
    try {
      const r = await api.post('/admin/rrhh', alta);
      toast.success(r.data?.mensaje || 'Persona dada de alta');
      setAlta(null);
      cargar();
    } catch (e) {
      // El backend explica POR QUÉ no se puede (por ejemplo, que tiene saldo).
      // Se muestra tal cual en vez de un "error al guardar" que no dice nada.
      toast.error(e?.response?.data?.detail || 'No se pudo dar de alta', { duration: 8000 });
    } finally {
      setGuardando(false);
    }
  };

  const verFicha = async (userId) => {
    try {
      const r = await api.get(`/admin/rrhh/${userId}`);
      setDetalle(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo abrir el legajo');
    }
  };

  const guardarPermisos = async () => {
    const { user_id, seleccion, motivo } = editandoPermisos;
    setGuardando(true);
    try {
      await api.put(`/admin/rrhh/${user_id}/permisos`, { permisos: seleccion, motivo });
      toast.success('Permisos actualizados');
      setEditandoPermisos(null);
      cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudieron guardar');
    } finally {
      setGuardando(false);
    }
  };

  const reenviar = async (ficha) => {
    // Se avisa qué implica antes de hacerlo: emitir una invitación nueva
    // ANULA la anterior, así que si la persona todavía tiene el correo viejo
    // a mano, ese enlace deja de servir.
    if (!await confirmar({
      titulo: `¿Reenviar la invitación a ${ficha.email}?`,
      detalle: 'El enlace anterior deja de funcionar apenas se manda el nuevo. '
        + 'El nuevo vence en 72 horas.',
      accion: 'Reenviar',
    })) return;
    try {
      const { data } = await api.post(`/admin/rrhh/${ficha.user_id}/reenviar-invitacion`);
      if (data?.acceso?.correo_enviado) {
        toast.success(data.mensaje);
      } else {
        toast.error('La invitación se emitió pero el correo no salió. Revisá la configuración de correo.');
      }
      await cargar();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'No se pudo reenviar la invitación');
    }
  };

  const darDeBaja = async (ficha) => {
    // El motivo NO es opcional: queda en el libro de auditoría y es lo único
    // que explica la baja meses después. Con `window.prompt` un motivo vacío
    // cancelaba en silencio y nadie entendía por qué no pasaba nada; acá el
    // botón queda apagado hasta que hay texto.
    const motivo = await pedirTexto({
      titulo: `¿Dar de baja a ${ficha.email}?`,
      detalle: 'Se le quitan los permisos, se desactiva la cuenta y se cierran '
        + 'sus sesiones. El usuario no se borra, para que el libro de auditoría '
        + 'siga teniendo sentido.',
      etiqueta: 'Motivo de la baja',
      placeholder: 'Queda asentado en el libro de auditoría',
      accion: 'Dar de baja',
      tono: 'peligro',
    });
    if (motivo === null) return;
    try {
      const r = await api.delete(`/admin/rrhh/${ficha.user_id}`, { data: { motivo } });
      toast.success(`Dado de baja · ${r.data?.sesiones_cerradas ?? 0} sesiones cerradas`);
      cargar();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'No se pudo dar de baja');
    }
  };

  const cajaPermisos = (seleccion, alTocar) => (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))',
      gap: 8, maxHeight: 260, overflowY: 'auto', border: '1px solid #e5e7eb',
      borderRadius: 8, padding: 12, background: '#fafafa',
    }}>
      {Object.entries(permisos).map(([clave, etiqueta]) => {
        // El catálogo del backend marca con "(MUEVE DINERO)" los tres
        // permisos que dejan tocar plata: ajustar saldos, aprobar recargas y
        // cargar fletes. Se destacan para que otorgarlos sea una decisión y
        // no un tilde más en una grilla de dieciocho casillas iguales.
        const mueveDinero = etiqueta.includes('MUEVE DINERO');
        const texto = etiqueta.replace(' (MUEVE DINERO)', '');
        return (
          <label
            key={clave}
            style={{
              display: 'flex', alignItems: 'center', gap: 8, fontSize: 13,
              cursor: 'pointer', borderRadius: 6, padding: '4px 6px',
              background: mueveDinero ? '#fff7ed' : 'transparent',
              border: mueveDinero ? '1px solid #fed7aa' : '1px solid transparent',
            }}
          >
            <input
              type="checkbox"
              checked={seleccion.includes(clave)}
              onChange={() => alTocar(seleccion.includes(clave)
                ? seleccion.filter((p) => p !== clave)
                : [...seleccion, clave])}
            />
            <span style={{ color: mueveDinero ? '#9a3412' : undefined }}>
              {texto}
              {mueveDinero && (
                <strong style={{ display: 'block', fontSize: 10.5, fontWeight: 700 }}>
                  MUEVE DINERO
                </strong>
              )}
            </span>
            <code style={{ fontSize: 11, color: '#9ca3af' }}>{clave}</code>
          </label>
        );
      })}
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Users size={20} color="#2563eb" />
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Recursos Humanos</h2>
        <span style={{ fontSize: 13, color: '#6b7280' }}>
          {personal.length} {personal.length === 1 ? 'persona' : 'personas'}
        </span>
        <div style={{ flex: 1 }} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <input type="checkbox" checked={incluirBajas}
                 onChange={(e) => setIncluirBajas(e.target.checked)} />
          Ver bajas
        </label>
        <button onClick={cargar} disabled={cargando}
                style={btn('#f3f4f6', '#111827')}>
          <RefreshCw size={15} className={cargando ? 'spin' : ''} /> Actualizar
        </button>
        <button onClick={() => setAlta({ ...VACIO })} style={btn('#2563eb', '#fff')}>
          <UserPlus size={15} /> Dar de alta
        </button>
      </div>

      <div style={{
        background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8,
        padding: '10px 14px', fontSize: 13, color: '#1e3a8a',
      }}>
        Las cuentas del personal <strong>no pueden hacer transacciones a título
        personal</strong>. Por eso no se puede dar de alta a alguien que tenga
        saldo: quedaría encerrado. Que lo retire antes.
      </div>

      {cargando ? (
        <p style={{ color: '#6b7280' }}>Cargando…</p>
      ) : personal.length === 0 ? (
        <p style={{ color: '#6b7280' }}>
          Todavía no hay personal dado de alta.
        </p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f9fafb', textAlign: 'left' }}>
                {['Persona', 'Cargo', 'Área', 'Permisos', 'Acceso', 'Alta', 'Estado', ''].map((h) => (
                  <th key={h} style={celdaCabecera}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {personal.map((p) => (
                <tr key={p.user_id} style={{ borderTop: '1px solid #f3f4f6' }}>
                  <td style={celda}>
                    <div style={{ fontWeight: 600 }}>{p.legajo?.nombre_completo || p.nombre || '—'}</div>
                    <div style={{ color: '#6b7280', fontSize: 12 }}>{p.email}</div>
                  </td>
                  <td style={celda}>{p.legajo?.cargo || '—'}</td>
                  <td style={celda}>{p.legajo?.area || '—'}</td>
                  <td style={celda}>
                    <span style={{
                      background: p.permisos.length ? '#dbeafe' : '#f3f4f6',
                      color: p.permisos.length ? '#1e40af' : '#6b7280',
                      padding: '2px 8px', borderRadius: 999, fontSize: 12,
                    }}>
                      {p.permisos.length}
                    </span>
                  </td>
                  <td style={celda}><Acceso acceso={p.acceso} /></td>
                  <td style={celda}>{fmtFecha(p.alta)}</td>
                  <td style={celda}>
                    {p.activo ? (
                      <span style={{ color: '#15803d' }}>Activo</span>
                    ) : (
                      <span style={{ color: '#b91c1c' }}>Baja {fmtFecha(p.baja)}</span>
                    )}
                  </td>
                  <td style={{ ...celda, whiteSpace: 'nowrap' }}>
                    <button onClick={() => verFicha(p.user_id)} style={btnChico}>
                      <History size={13} /> Legajo
                    </button>
                    {p.activo && (
                      <>
                        <button
                          onClick={() => setEditandoPermisos({
                            user_id: p.user_id, email: p.email,
                            seleccion: [...p.permisos], motivo: '',
                          })}
                          style={btnChico}>
                          <ShieldCheck size={13} /> Permisos
                        </button>
                        {!p.acceso?.clave_configurada && (
                          <button onClick={() => reenviar(p)} style={btnChico}>
                            <Mail size={13} /> Reenviar
                          </button>
                        )}
                        <button onClick={() => darDeBaja(p)}
                                style={{ ...btnChico, color: '#b91c1c' }}>
                          <Trash2 size={13} /> Baja
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Alta ─────────────────────────────────────────────────────── */}
      {alta && (
        <Modal titulo="Dar de alta personal" alCerrar={() => setAlta(null)}>
          <div style={{ display: 'grid', gap: 12 }}>
            {[
              ['email', 'Correo *', 'correo@empresa.com'],
              ['nombre_completo', 'Nombre completo *', ''],
              ['cargo', 'Cargo *', 'Analista de soporte'],
              ['area', 'Área *', 'Atención al cliente'],
              ['documento', 'Documento', ''],
              ['telefono', 'Teléfono', ''],
              ['fecha_ingreso', 'Fecha de ingreso', 'AAAA-MM-DD'],
            ].map(([campo, etiqueta, ph]) => (
              <label key={campo} style={{ display: 'grid', gap: 4, fontSize: 13 }}>
                <span style={{ fontWeight: 600 }}>{etiqueta}</span>
                <input
                  value={alta[campo]} placeholder={ph}
                  onChange={(e) => setAlta({ ...alta, [campo]: e.target.value })}
                  style={entrada}
                />
              </label>
            ))}
            <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
              <span style={{ fontWeight: 600 }}>Notas</span>
              <textarea
                value={alta.notas} rows={2}
                onChange={(e) => setAlta({ ...alta, notas: e.target.value })}
                style={{ ...entrada, resize: 'vertical' }}
              />
            </label>
            <div style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>
                Permisos ({alta.permisos.length} de {Object.keys(permisos).length})
              </span>
              {cajaPermisos(alta.permisos, (s) => setAlta({ ...alta, permisos: s }))}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
            <button onClick={() => setAlta(null)} style={btn('#f3f4f6', '#111827')}>Cancelar</button>
            <button onClick={darDeAlta} disabled={guardando} style={btn('#2563eb', '#fff')}>
              <Save size={15} /> {guardando ? 'Guardando…' : 'Dar de alta'}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Permisos ─────────────────────────────────────────────────── */}
      {editandoPermisos && (
        <Modal titulo={`Permisos · ${editandoPermisos.email}`}
               alCerrar={() => setEditandoPermisos(null)}>
          {cajaPermisos(editandoPermisos.seleccion,
            (s) => setEditandoPermisos({ ...editandoPermisos, seleccion: s }))}
          <label style={{ display: 'grid', gap: 4, fontSize: 13, marginTop: 12 }}>
            <span style={{ fontWeight: 600 }}>Motivo del cambio</span>
            <input
              value={editandoPermisos.motivo}
              placeholder="Queda asentado en el libro de auditoría"
              onChange={(e) => setEditandoPermisos({ ...editandoPermisos, motivo: e.target.value })}
              style={entrada}
            />
          </label>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
            <button onClick={() => setEditandoPermisos(null)} style={btn('#f3f4f6', '#111827')}>Cancelar</button>
            <button onClick={guardarPermisos} disabled={guardando} style={btn('#2563eb', '#fff')}>
              <Save size={15} /> {guardando ? 'Guardando…' : 'Guardar'}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Legajo ───────────────────────────────────────────────────── */}
      {detalle && (
        <Modal titulo={`Legajo · ${detalle.ficha?.email}`} alCerrar={() => setDetalle(null)} ancho={760}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10, fontSize: 13 }}>
            {[
              ['Nombre', detalle.ficha?.legajo?.nombre_completo],
              ['Cargo', detalle.ficha?.legajo?.cargo],
              ['Área', detalle.ficha?.legajo?.area],
              ['Documento', detalle.ficha?.legajo?.documento],
              ['Teléfono', detalle.ficha?.legajo?.telefono],
              ['Ingreso', detalle.ficha?.legajo?.fecha_ingreso],
              ['Alta en el sistema', fmtFecha(detalle.ficha?.alta)],
              ['Permisos', (detalle.ficha?.permisos || []).length],
            ].map(([k, v]) => (
              <div key={k}>
                <div style={{ color: '#6b7280', fontSize: 12 }}>{k}</div>
                <div style={{ fontWeight: 600 }}>{v || '—'}</div>
              </div>
            ))}
          </div>
          {detalle.ficha?.legajo?.notas && (
            <p style={{ fontSize: 13, marginTop: 12, color: '#374151' }}>
              {detalle.ficha.legajo.notas}
            </p>
          )}
          <h4 style={{ marginTop: 20, marginBottom: 8, fontSize: 14 }}>
            Historial · {(detalle.historial || []).length} movimientos
          </h4>
          {(detalle.historial || []).length === 0 ? (
            <p style={{ color: '#6b7280', fontSize: 13 }}>Sin movimientos registrados.</p>
          ) : (
            <div style={{ maxHeight: 300, overflowY: 'auto', fontSize: 12 }}>
              {detalle.historial.map((l, i) => (
                <div key={i} style={{ borderTop: '1px solid #f3f4f6', padding: '8px 0' }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
                    <strong>{l.etiqueta}</strong>
                    <span style={{ color: '#6b7280' }}>{fmtFecha(l.cuando)}</span>
                    <span style={{ color: '#9ca3af' }}>por {l.actor?.email || '—'}</span>
                  </div>
                  {(l.antes || l.despues) && (
                    <div style={{ color: '#6b7280', marginTop: 2 }}>
                      <code>{JSON.stringify(l.antes)}</code> → <code>{JSON.stringify(l.despues)}</code>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}

// Un solo vistazo para saber si alguien con permisos de administración
// todavía no terminó de asegurar su cuenta. Una persona con permisos y sin
// dos pasos es exactamente lo que hay que poder ver desde acá.
function Acceso({ acceso }) {
  if (!acceso) return <span style={{ color: '#6b7280' }}>—</span>;

  const estado = acceso.invitacion?.estado;
  let texto;
  let color;
  if (!acceso.clave_configurada) {
    if (estado === 'pendiente') { texto = 'Invitación enviada'; color = '#b45309'; }
    else if (estado === 'vencida') { texto = 'Invitación vencida'; color = '#b91c1c'; }
    else { texto = 'Sin invitación'; color = '#b91c1c'; }
  } else if (!acceso.dos_pasos) {
    texto = 'Sin 2FA';
    color = '#b45309';
  } else {
    texto = 'Activo con 2FA';
    color = '#15803d';
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5, color }}>
      {acceso.dos_pasos ? <ShieldCheck size={13} /> : <AlertTriangle size={13} />}
      <span style={{ fontSize: 12 }}>{texto}</span>
    </div>
  );
}

function Modal({ titulo, alCerrar, ancho = 620, children }) {
  return (
    <div onClick={alCerrar} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000, padding: 16,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: '#fff', borderRadius: 12, padding: 20,
        width: '100%', maxWidth: ancho, maxHeight: '90vh', overflowY: 'auto',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, flex: 1 }}>{titulo}</h3>
          <button onClick={alCerrar} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

const celdaCabecera = { padding: '8px 10px', fontWeight: 600, color: '#374151', fontSize: 12 };
const celda = { padding: '10px' };
const entrada = {
  padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13,
};
const btnChico = {
  display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 8px',
  marginRight: 6, background: '#f3f4f6', border: '1px solid #e5e7eb',
  borderRadius: 6, fontSize: 12, cursor: 'pointer',
};
function btn(fondo, color) {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 14px',
    background: fondo, color, border: 'none', borderRadius: 8,
    fontSize: 13, fontWeight: 600, cursor: 'pointer',
  };
}
