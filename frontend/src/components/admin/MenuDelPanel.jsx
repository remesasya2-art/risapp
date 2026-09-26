// components/admin/MenuDelPanel.jsx — El menú del costado del panel.
//
// Vivía adentro de pages/AdminPanel.jsx, que está congelado en 2525 líneas
// por la regla de las 800: se movió tal cual para poder separar el panel por
// servicio. Las secciones y los grupos que dibuja están en
// seccionesDelPanel.js.
import { useEffect, useState } from 'react';
import { ChevronRight } from 'lucide-react';
import api from '../../utils/api';
import {
  GRUPOS, POR_CLAVE, SERVICIOS_DEL_PANEL, SERVICIO_DE, puedeVerSeccion,
} from './seccionesDelPanel';

// El número que dice cuánto espera en una pestaña.
//
// Se pinta SOLO si hay algo. Un «0» permanente en nueve pestañas es ruido que
// se aprende a no mirar, y entonces el 3 de al lado tampoco se mira.
function Pendiente({ cuantos, activa }) {
  if (!cuantos) return null;
  return (
    <span
      style={{
        minWidth: '20px', height: '20px', padding: '0 6px', borderRadius: '9999px',
        fontSize: '11px', fontWeight: 700, display: 'inline-flex',
        alignItems: 'center', justifyContent: 'center',
        backgroundColor: activa ? 'rgba(255,255,255,0.28)' : 'var(--en-oscuro-error-suave, #fee2e2)',
        color: activa ? '#ffffff' : 'var(--en-oscuro-error, #b91c1c)',
      }}
      data-testid="pendiente"
    >
      {cuantos > 99 ? '99+' : cuantos}
    </span>
  );
}

export default function MenuDelPanel({
  user, activeTab, irA, abrirSeccion, pendientes, esAncho, menuAbierto, setMenuAbierto,
}) {
  // Los permisos de quien mira, para mostrarle sólo lo que el servidor le va
  // a dejar abrir. Ver `puedeVerSeccion` en seccionesDelPanel.js.
  const [permisos, setPermisos] = useState(null);
  useEffect(() => {
    let vigente = true;
    if (user?.role === 'super_admin') return undefined;
    api.get('/admin/mi-acceso')
      .then((r) => { if (vigente) setPermisos(r.data?.permisos || []); })
      .catch(() => { if (vigente) setPermisos([]); });
    return () => { vigente = false; };
  }, [user?.role]);

  // Las reglas de quién ve qué, en un solo lugar: seccionesDelPanel.js.
  const gruposVisibles = GRUPOS
    .map((g) => ({ ...g, hijas: g.hijas.filter((c) => puedeVerSeccion(c, user?.role, permisos)) }))
    .filter((g) => g.hijas.length > 0);

  // EL CONTADOR SUBE AL GRUPO, Y NO ES UN ADORNO
  //
  //   El número que dice cuánto espera vivía en la pestaña de cada sección, y
  //   eso se hizo a propósito: quien entra al panel tiene que ver DESDE AFUERA
  //   dónde hay cola. Al agrupar, ese número queda un nivel más adentro.
  //
  //   Así que el grupo muestra la suma y cada sección conserva el suyo:
  //   «Operación 7» se ve de entrada, y al abrirlo se ve que son 4 de Órdenes
  //   y 3 de Retiros. Sin esto, agrupar escondería justo la señal que dice por
  //   dónde empezar.
  const pendientesDe = (clave) => pendientes[clave] || 0;

  const pendientesDelGrupo = (grupo) =>
    grupo.hijas.reduce((suma, clave) => suma + pendientesDe(clave), 0);

  // LOS CUATRO SERVICIOS
  //
  //   El menú muestra los grupos de UN servicio por vez: el de la sección
  //   abierta. Así, al llegar a una sección desde la campana o desde un
  //   enlace con `?tab=`, el botón de su servicio se enciende solo, y no
  //   hace falta un estado aparte que pueda quedar desparejo.
  //
  //   Se muestran sólo los servicios en los que esta persona ve alguna
  //   sección, y los botones sólo si son más de uno: a un agente, que ve
  //   clientes y la cola de envíos, no se le ofrece el banco.
  const serviciosVisibles = SERVICIOS_DEL_PANEL.filter(
    (s) => gruposVisibles.some((g) => g.servicio === s.key));
  const servicioActual = SERVICIO_DE[activeTab] || serviciosVisibles[0]?.key;
  const gruposDelServicio = gruposVisibles.filter((g) => g.servicio === servicioActual);

  // Elegir un servicio abre su primera sección, sin cerrar el menú del
  // teléfono: se eligió un menú, todavía no qué hacer en él.
  const elegirServicio = (clave) => {
    const primero = gruposVisibles.find((g) => g.servicio === clave);
    if (primero && clave !== servicioActual) abrirSeccion(primero.hijas[0]);
  };

  // Si cada servicio está prendido. Lo mira todo el personal: quien atiende
  // tiene que saber que remesas está en pausa antes de que un cliente se lo
  // cuente. Se vuelve a pedir al cambiar de sección, como los pendientes,
  // así que después de apagar uno en «Servicios» el menú se entera enseguida.
  const [encendidos, setEncendidos] = useState({});
  useEffect(() => {
    let vigente = true;
    api.get('/admin/servicios')
      .then((r) => {
        if (!vigente) return;
        setEncendidos(Object.fromEntries(
          (r.data?.servicios || []).map((s) => [s.servicio, s])));
      })
      .catch(() => { /* sin el dato, los botones van sin la marca */ });
    return () => { vigente = false; };
  }, [activeTab]);

  const pendientesDelServicio = (clave) => gruposVisibles
    .filter((g) => g.servicio === clave)
    .reduce((suma, g) => suma + pendientesDelGrupo(g), 0);

  // QUE GRUPOS ESTAN DESPLEGADOS
  //
  //   Arrancan TODOS CERRADOS. Es una decisión del dueño del proyecto y va
  //   anotada porque la primera versión hacía lo contrario: los abría todos,
  //   con el argumento de que el menú existe para ver las veinte secciones sin
  //   tocar nada.
  //
  //   Lo que ese argumento no miraba: veinte renglones abiertos no se leen de
  //   un vistazo, se recorren. Con los grupos cerrados, el menú entero son
  //   SEIS renglones que entran juntos en cualquier pantalla —teléfono
  //   incluido—, y se despliega el que se necesita. Eso es lo que hace que
  //   agrupar sirva de algo en vez de ser sólo un título encima de una lista
  //   igual de larga.
  //
  //   Cada grupo se abre y se cierra por su cuenta: se pueden tener dos
  //   abiertos a la vez. Cerrar los otros al abrir uno es la otra forma
  //   posible, y se descartó porque obliga a reabrir el de al lado cada vez
  //   que se va y se vuelve.
  //
  //   El grupo de la sección abierta se despliega solo y no se puede cerrar:
  //   esconder justo lo que estás mirando deja el menú sin poder indicar dónde
  //   estás parada.
  const [desplegados, setDesplegados] = useState(() => new Set());

  const desplegar = (clave) => setDesplegados((antes) => {
    const ahora = new Set(antes);
    if (ahora.has(clave)) ahora.delete(clave); else ahora.add(clave);
    return ahora;
  });

  return (
    <>
      {/* La sombra que tapa el contenido mientras el menú está abierto. Se
          toca y se cierra: en un teléfono es más fácil que buscar la X. */}
      {!esAncho && menuAbierto && (
        <div onClick={() => setMenuAbierto(false)}
          style={{ position: 'fixed', inset: '64px 0 0 0', zIndex: 45,
                   backgroundColor: 'rgba(17,24,39,0.45)' }} />
      )}
      <aside style={{
        width: '236px', flexShrink: 0, backgroundColor: 'var(--en-oscuro-superficie, #ffffff)',
        borderRight: '1px solid var(--en-oscuro-linea, #e5e7eb)', padding: '18px 12px',
        overflowY: 'auto',
        ...(esAncho ? {
          minHeight: 'calc(100vh - 64px)', position: 'sticky', top: '64px',
          maxHeight: 'calc(100vh - 64px)',
        } : {
          position: 'fixed', top: '64px', bottom: 0, left: 0, zIndex: 50,
          boxShadow: '2px 0 16px rgba(0,0,0,0.12)',
          transform: menuAbierto ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.2s ease',
        }),
      }}>
        {serviciosVisibles.length > 1 && (
          <div data-testid="servicios-del-panel" style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px',
            marginBottom: '14px', paddingBottom: '14px',
            borderBottom: '1px solid var(--en-oscuro-linea, #e5e7eb)',
          }}>
            {serviciosVisibles.map((s) => {
              const activo = s.key === servicioActual;
              const estado = encendidos[s.key];
              const apagado = estado && !estado.encendido;
              return (
                <button key={s.key} onClick={() => elegirServicio(s.key)}
                  data-testid={`servicio-${s.key}`}
                  title={estado ? `${s.label}: ${estado.estado}` : s.label}
                  style={{
                    position: 'relative', display: 'flex', flexDirection: 'column',
                    alignItems: 'center', gap: '3px', padding: '8px 4px', borderRadius: '10px',
                    cursor: 'pointer', fontSize: '12px', fontWeight: activo ? 700 : 600,
                    border: activo ? '1.5px solid var(--en-oscuro-acento, #4f46e5)' : '1px solid var(--en-oscuro-linea, #e5e7eb)',
                    backgroundColor: activo ? 'var(--en-oscuro-acento-suave, #eef2ff)' : 'transparent',
                    color: activo ? 'var(--en-oscuro-acento, #4338ca)' : 'var(--en-oscuro-texto-2, #4b5563)',
                  }}>
                  <s.icon style={{ width: '16px', height: '16px' }} />
                  <span>{s.label}</span>
                  {apagado && (
                    <span data-testid={`servicio-${s.key}-apagado`} style={{
                      fontSize: '10px', fontWeight: 700, textTransform: 'uppercase',
                      letterSpacing: '0.04em', color: 'var(--en-oscuro-texto-3, #9ca3af)',
                    }}>{estado.estado}</span>
                  )}
                  {!activo && pendientesDelServicio(s.key) > 0 && (
                    <span style={{ position: 'absolute', top: '4px', right: '4px' }}>
                      <Pendiente cuantos={pendientesDelServicio(s.key)} activa={false} />
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
        {gruposDelServicio.map((grupo) => {
          // El grupo de la sección abierta no se pliega, aunque se haya
          // pedido: el menú tiene que poder mostrar dónde estás parada.
          const tieneLoAbierto = grupo.hijas.includes(activeTab);
          const abierto = tieneLoAbierto || desplegados.has(grupo.key);
          return (
          <div key={grupo.key} style={{
            marginBottom: '10px', paddingBottom: '10px',
            // La línea entre grupos. Antes la separación era sólo aire, y el
            // aire no se lee como una división: los títulos en gris chiquito
            // se veían como espacio sobrante y el menú parecía una lista
            // larga y plana de veinte cosas sueltas.
            borderBottom: '1px solid var(--en-oscuro-linea, #f1f2f6)',
          }}>
            <button onClick={() => desplegar(grupo.key)}
              data-testid={`grupo-${grupo.key}`}
              style={{
                display: 'flex', alignItems: 'center', gap: '8px', width: '100%',
                padding: '7px 10px', marginBottom: '3px', borderRadius: '8px',
                border: 'none', backgroundColor: 'transparent', cursor: 'pointer',
                fontSize: '11.5px', fontWeight: 800, color: 'var(--en-oscuro-texto, #111827)',
                textTransform: 'uppercase', letterSpacing: '0.06em',
              }}>
              <grupo.icon style={{ width: '14px', height: '14px', color: 'var(--en-oscuro-acento, #6366f1)' }} />
              <span style={{ flex: 1, textAlign: 'left' }}>{grupo.label}</span>
              <Pendiente cuantos={pendientesDelGrupo(grupo)} activa={false} />
              <ChevronRight style={{
                width: '14px', height: '14px', color: 'var(--en-oscuro-texto-3, #c2c6d0)',
                transform: abierto ? 'rotate(90deg)' : 'none',
                transition: 'transform 0.15s',
              }} />
            </button>
            {abierto && grupo.hijas.map((clave) => {
              const s = POR_CLAVE[clave];
              if (!s) return null;
              const activa = activeTab === clave;
              return (
                <button key={clave} onClick={() => irA(clave)}
                  data-testid={`tab-${clave}`}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '9px', width: '100%',
                    padding: '8px 10px', marginBottom: '2px', borderRadius: '9px',
                    border: 'none', cursor: 'pointer', textAlign: 'left',
                    fontSize: '13.5px', fontWeight: activa ? 600 : 500,
                    backgroundColor: activa ? 'var(--en-oscuro-acento-suave, #eef2ff)' : 'transparent',
                    color: activa ? 'var(--en-oscuro-acento, #4338ca)' : 'var(--en-oscuro-texto-2, #4b5563)',
                  }}
                >
                  <s.icon style={{ width: '16px', height: '16px', flexShrink: 0 }} />
                  <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden',
                                 textOverflow: 'ellipsis' }}>{s.label}</span>
                  <Pendiente cuantos={pendientesDe(clave)} activa={false} />
                </button>
              );
            })}
          </div>
        );})}
      </aside>
    </>
  );
}
