/**
 * pages/Referidos.jsx — A quién invité, y qué cobré por cada uno.
 *
 * QUE MUESTRA DE CADA PERSONA, Y QUE NO
 *
 *   El nombre de pila con la inicial del apellido, el mes en que se registró,
 *   y el estado del bono con su motivo. Nada más: la lista NO trae el correo
 *   de nadie, y el servidor tampoco lo manda.
 *
 *   El motivo sí se muestra —«le falta verificar su identidad»— y eso le
 *   cuenta a una persona algo del estado de otra. Fue decisión del dueño del
 *   proyecto, y está tomada con el motivo a la vista: sin el motivo la
 *   pantalla no sirve para lo único que se le pide, que es saber a quién
 *   recordarle.
 *
 * LOS NUMEROS LOS CUENTA LA BASE
 *
 *   No se cuentan acá sobre la lista, porque la lista viene paginada: con
 *   cuarenta referidos, contar sobre los veinte de la primera página daría un
 *   número que se contradice con el de abajo.
 *
 * LO GANADO SALE DEL LIBRO
 *
 *   Y no de multiplicar los cobrados por el monto de hoy. El monto se
 *   configura desde el panel y puede haber cambiado entre un cobro y otro.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, Clock, Users } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { Boton } from '../components/flujo';
import { C, HOJA, tarjeta, microEtiqueta } from '../components/flujo/estilos';

export default function Referidos() {
  const navigate = useNavigate();
  const [datos, setDatos] = useState(null);
  const [pagina, setPagina] = useState(1);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let vivo = true;
    (async () => {
      setCargando(true);
      try {
        const r = await api.get('/referidos/mis-referidos', { params: { pagina } });
        if (vivo) setDatos(r.data);
      } catch (e) {
        if (vivo) toast.error(e?.response?.data?.detail
          || 'No se pudo leer tu lista de invitados');
      } finally {
        if (vivo) setCargando(false);
      }
    })();
    return () => { vivo = false; };
  }, [pagina]);

  const numeros = [
    { etiqueta: 'Invitados', valor: datos?.total ?? '—' },
    { etiqueta: 'Con bono cobrado', valor: datos?.cobrados ?? '—' },
    { etiqueta: 'Pendientes', valor: datos?.pendientes ?? '—' },
    {
      etiqueta: 'Ganado',
      valor: datos ? `R$ ${Number(datos.ganado || 0).toLocaleString('pt-BR', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
      })}` : '—',
    },
  ];

  return (
    <div className="env" data-testid="pagina-referidos" style={{
      minHeight: '100vh', background: C.fondo,
      fontFamily: 'Inter, -apple-system, Segoe UI, Roboto, sans-serif',
    }}>
      <style>{HOJA}</style>

      <div style={{ maxWidth: '640px', margin: '0 auto', padding: '20px 16px 44px' }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '18px' }}>
          <button type="button" onClick={() => navigate(-1)} aria-label="Volver"
            className="env-tap" data-testid="volver-de-referidos"
            style={{
              width: '42px', height: '42px', borderRadius: '11px', flexShrink: 0,
              border: `1px solid ${C.linea}`, background: C.lienzo, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
            <ArrowLeft size={19} color={C.texto} />
          </button>
          <h1 style={{
            fontSize: '21px', fontWeight: 700, color: C.tinta, margin: 0,
            letterSpacing: '-.01em',
          }}>
            A quién invité
          </h1>
        </div>

        {/* ── Los cuatro números ─────────────────────────────────────────── */}
        <section style={{
          ...tarjeta, padding: '18px 20px', marginBottom: '16px',
          display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
          gap: '16px',
        }}>
          {numeros.map((n) => (
            <div key={n.etiqueta} data-testid={`numero-${n.etiqueta}`}>
              <span style={microEtiqueta}>{n.etiqueta}</span>
              <div style={{
                fontSize: '22px', fontWeight: 700, color: C.tinta,
                fontVariantNumeric: 'tabular-nums', marginTop: '2px',
              }}>
                {n.valor}
              </div>
            </div>
          ))}
        </section>

        {/* ── La lista ───────────────────────────────────────────────────── */}
        {cargando && !datos ? (
          <p style={{ textAlign: 'center', color: C.suave, padding: '28px 0' }}>
            Cargando…
          </p>
        ) : !datos?.referidos?.length ? (
          <section style={{ ...tarjeta, padding: '32px 20px', textAlign: 'center' }}>
            <Users size={26} color={C.tenue} />
            <p style={{ margin: '10px 0 0', fontSize: '15px', fontWeight: 600, color: C.tinta }}>
              Todavía no invitaste a nadie
            </p>
            <p style={{ margin: '4px 0 0', fontSize: '13px', color: C.suave }}>
              Compartí tu enlace desde tu perfil y acá vas a ver a quién se registró con él.
            </p>
          </section>
        ) : (
          <section style={{ ...tarjeta, overflow: 'hidden' }}>
            {datos.referidos.map((r, i) => (
              <div key={`${r.nombre}-${i}`}
                data-testid="fila-de-referido"
                style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  padding: '14px 18px',
                  borderTop: i === 0 ? 'none' : `1px solid ${C.linea}`,
                }}>
                <span style={{
                  width: '34px', height: '34px', borderRadius: '10px', flexShrink: 0,
                  background: r.cobrado ? C.exitoSuave : C.fondo,
                  border: `1px solid ${r.cobrado ? C.exitoBorde : C.linea}`,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {r.cobrado ? <Check size={16} color={C.exito} />
                             : <Clock size={15} color={C.suave} />}
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{
                    display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.tinta,
                  }}>
                    {r.nombre}
                  </span>
                  <span style={{
                    display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px',
                  }}>
                    {r.cuando}
                  </span>
                </span>
                <span style={{
                  fontSize: '12px', fontWeight: 600, textAlign: 'right',
                  color: r.cobrado ? C.exito : C.suave, maxWidth: '46%',
                }}>
                  {r.motivo}
                </span>
              </div>
            ))}
          </section>
        )}

        {/* ── Paginación ─────────────────────────────────────────────────── */}
        {datos && (pagina > 1 || datos.hay_mas) ? (
          <div style={{
            display: 'flex', gap: '9px', marginTop: '16px', alignItems: 'center',
          }}>
            <Boton onClick={() => setPagina((p) => Math.max(1, p - 1))}
              disabled={pagina <= 1 || cargando} testid="referidos-anterior">
              Anterior
            </Boton>
            <span style={{ fontSize: '13px', color: C.suave, flex: 1, textAlign: 'center' }}>
              Página {pagina}
            </span>
            <Boton onClick={() => setPagina((p) => p + 1)}
              disabled={!datos.hay_mas || cargando} testid="referidos-siguiente">
              Siguiente
            </Boton>
          </div>
        ) : null}
      </div>
    </div>
  );
}
