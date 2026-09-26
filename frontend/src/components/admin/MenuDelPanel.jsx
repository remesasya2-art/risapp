// components/admin/MenuDelPanel.jsx — El menú del costado del panel.
//
// Vivía adentro de pages/AdminPanel.jsx, que está congelado en 2525 líneas
// por la regla de las 800: se movió tal cual para poder separar el panel por
// servicio. Las secciones y los grupos que dibuja están en
// seccionesDelPanel.js.
import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { GRUPOS, POR_CLAVE } from './seccionesDelPanel';

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
  user, activeTab, irA, pendientes, esAncho, menuAbierto, setMenuAbierto,
}) {
  const isAgent = user?.role === 'agent';

  // CRM no tiene trabajo propio: es la puerta a KYC, Soporte y las demás. Su
  // número es la suma de lo que hay adentro, o la pestaña se ve vacía mientras
  // hay ocho KYC esperando a un clic de distancia.
  // Las mismas reglas de siempre, en un solo lugar en vez de repartidas entre
  // la tira de arriba y la de las subpestañas.
  const puedeVerSeccion = (clave) => {
    if (isAgent) {
      return ['chat', 'support', 'users', 'kyc', 'blacklist', 'operacion']
        .includes(clave);
    }
    if (clave === 'ratings') return user?.role === 'super_admin';
    return !POR_CLAVE[clave]?.superAdminOnly || user?.role === 'super_admin';
  };

  const gruposVisibles = GRUPOS
    .map((g) => ({ ...g, hijas: g.hijas.filter(puedeVerSeccion) }))
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
        {gruposVisibles.map((grupo) => {
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
