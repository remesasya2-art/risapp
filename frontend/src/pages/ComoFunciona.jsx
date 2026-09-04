/**
 * ComoFunciona.jsx — NO SE PUBLICA.
 *
 *   Esta página no tiene ruta y no se llega a ella desde ningún lado. Se armó
 *   como material interno y se decidió que no salga a la web: describe con
 *   detalle cómo opera la plataforma por dentro, y ese nivel de detalle no va
 *   publicado.
 *
 *   Se conserva el archivo por si algún día se sirve dentro de la aplicación,
 *   con sesión iniciada. Volver a ponerle una ruta pública es una decisión del
 *   operador, no un arreglo; `test_lo_que_no_se_publica.py` la frena.
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  ShieldCheck, ScrollText, IdCard, Gauge, Lock, MessageSquare, ArrowRight,
} from 'lucide-react';
import Footer from '../components/Footer';
import api from '../utils/api';

const MORADO = '#5B4FE9';

function moneda(valor, simbolo) {
  if (valor === null || valor === undefined) return null;
  return `${simbolo} ${Number(valor).toLocaleString('es-VE', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

// El ícono llega ya renderizado y no como componente: el linter de este
// repositorio no cuenta el uso en JSX de un parámetro destructurado, y
// pasarlo así evita la excepción sin apagar la regla.
function Tarjeta({ icono, titulo, children }) {
  return (
    <div style={{
      border: '1px solid #ececf3', borderRadius: 14, padding: 22,
      background: '#fff', display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10, background: '#f0eeff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {icono}
        </div>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#111827' }}>{titulo}</h3>
      </div>
      <div style={{ fontSize: 14, color: '#4b5563', lineHeight: 1.65 }}>{children}</div>
    </div>
  );
}

function Dato({ etiqueta, valor }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', gap: 16,
      padding: '9px 0', borderBottom: '1px solid #f3f4f6', fontSize: 14,
    }}>
      <span style={{ color: '#6b7280' }}>{etiqueta}</span>
      <strong style={{ color: '#111827', textAlign: 'right' }}>{valor}</strong>
    </div>
  );
}

export default function ComoFunciona() {
  const [limites, setLimites] = useState(null);
  const [falloLaConsulta, setFalloLaConsulta] = useState(false);

  useEffect(() => {
    let vigente = true;
    api.get('/limits')
      .then((r) => { if (vigente) setLimites(r.data); })
      .catch(() => { if (vigente) setFalloLaConsulta(true); })
      .finally(() => {});
    return () => { vigente = false; };
  }, []);

  const pix = limites?.pix;
  const ves = limites?.ves;
  const cupo = limites?.sin_verificar;

  return (
    <div style={{ minHeight: '100vh', background: '#fff', fontFamily: 'Inter, Helvetica, -apple-system, sans-serif' }}>
      <header style={{
        position: 'sticky', top: 0, zIndex: 20, background: 'rgba(255,255,255,0.92)',
        backdropFilter: 'blur(8px)', borderBottom: '1px solid #f0f0f5', padding: '14px 20px',
      }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          <Link to="/" style={{ fontWeight: 800, fontSize: 17, color: '#111827', textDecoration: 'none' }}>
            RIS App
          </Link>
          <div style={{ flex: 1 }} />
          <Link to="/legal" style={{ fontSize: 14, color: '#374151', textDecoration: 'none' }}>Legal</Link>
          <Link to="/login" style={{
            padding: '9px 18px', borderRadius: 10, fontSize: 14, fontWeight: 600,
            color: '#fff', textDecoration: 'none',
            background: `linear-gradient(135deg, ${MORADO} 0%, #3B3A9E 100%)`,
          }}>
            Entrar
          </Link>
        </div>
      </header>

      <section style={{ padding: '52px 20px 32px', background: 'radial-gradient(ellipse at top left, #f0eeff 0%, #ffffff 55%)' }}>
        <div style={{ maxWidth: 780, margin: '0 auto' }}>
          <h1 style={{ fontSize: 38, fontWeight: 800, color: '#111827', lineHeight: 1.15, margin: '0 0 14px 0' }}>
            Cómo funciona
          </h1>
          <p style={{ fontSize: 17, color: '#6b7280', lineHeight: 1.6, margin: 0 }}>
            Qué hace la plataforma, con qué límites opera, qué verificación pide
            y qué queda registrado de cada operación. Los montos de esta página
            se leen del sistema en vivo: son los mismos que se aplican al operar.
          </p>
        </div>
      </section>

      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '8px 20px 40px' }}>

        {/* ── Límites, en vivo ─────────────────────────────────────────── */}
        <h2 style={{ fontSize: 22, fontWeight: 700, color: '#111827', margin: '28px 0 14px' }}>
          Límites por operación
        </h2>

        {falloLaConsulta ? (
          <div style={{
            border: '1px solid #fde68a', background: '#fffbeb', borderRadius: 12,
            padding: 18, fontSize: 14, color: '#92400e',
          }}>
            No se pudieron cargar los límites en este momento. No se muestran
            valores de referencia a propósito: un monto equivocado acá sería una
            promesa que la plataforma no puede cumplir. Volvé a intentar en unos
            minutos, o escribinos y te los confirmamos.
          </div>
        ) : !limites ? (
          <p style={{ color: '#9ca3af', fontSize: 14 }}>Cargando…</p>
        ) : (
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 18,
          }}>
            <div style={{ border: '1px solid #ececf3', borderRadius: 14, padding: 22 }}>
              <h3 style={{ margin: '0 0 10px', fontSize: 16, fontWeight: 700 }}>Recarga en reales (PIX)</h3>
              <Dato etiqueta="Mínimo por operación" valor={moneda(pix?.min_brl, 'R$')} />
              <Dato etiqueta="Máximo por operación" valor={moneda(pix?.max_brl, 'R$')} />
            </div>
            <div style={{ border: '1px solid #ececf3', borderRadius: 14, padding: 22 }}>
              <h3 style={{ margin: '0 0 10px', fontSize: 16, fontWeight: 700 }}>Recarga en bolívares</h3>
              <Dato etiqueta="Mínimo por operación" valor={moneda(ves?.min_ves, 'Bs')} />
              <Dato
                etiqueta="Máximo por operación"
                valor={ves?.max_ves === null || ves?.max_ves === undefined
                  ? 'Sin tope fijado'
                  : moneda(ves?.max_ves, 'Bs')}
              />
            </div>
          </div>
        )}

        {/* ── Verificación ─────────────────────────────────────────────── */}
        <h2 style={{ fontSize: 22, fontWeight: 700, color: '#111827', margin: '36px 0 14px' }}>
          Verificación de identidad
        </h2>
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 18,
        }}>
          <Tarjeta icono={<IdCard size={18} color={MORADO} />} titulo="Antes de verificar">
            {cupo ? (
              <>
                Se puede operar con un cupo inicial de{' '}
                <strong>{moneda(cupo.max_ris, 'R$')}</strong> acumulados y hasta{' '}
                <strong>{cupo.max_operaciones}</strong>{' '}
                {cupo.max_operaciones === 1 ? 'operación' : 'operaciones'}.
                Al agotarse, la plataforma pide la verificación para continuar.
              </>
            ) : (
              'Existe un cupo inicial limitado antes de verificar la identidad.'
            )}
          </Tarjeta>
          <Tarjeta icono={<ShieldCheck size={18} color={MORADO} />} titulo="Qué se pide">
            Documento de identidad con su reverso cuando el tipo de documento lo
            tiene, comprobante de CPF y una selfie. Si algo no se lee bien, se
            rechaza indicando el motivo y se puede volver a enviar.
          </Tarjeta>
        </div>

        {/* ── Controles ────────────────────────────────────────────────── */}
        <h2 style={{ fontSize: 22, fontWeight: 700, color: '#111827', margin: '36px 0 14px' }}>
          Qué queda registrado
        </h2>
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 18,
        }}>
          <Tarjeta icono={<ScrollText size={18} color={MORADO} />} titulo="Cada movimiento de saldo">
            Toda entrada y salida de saldo deja un asiento contable con su
            fecha, su monto, su motivo y la operación que lo originó. Un asiento
            no se borra ni se reescribe: si algo se corrige, la corrección es un
            asiento más.
          </Tarjeta>
          <Tarjeta icono={<Gauge size={18} color={MORADO} />} titulo="Cada intervención del equipo">
            Cuando alguien del equipo interviene sobre una cuenta, queda
            asentado con quién lo hizo y cuándo. Si querés saber qué pasó con
            una operación tuya, podés pedir ese detalle desde el{' '}
            <Link to="/support" style={{ color: MORADO }}>centro de ayuda</Link>.
          </Tarjeta>
          <Tarjeta icono={<Lock size={18} color={MORADO} />} titulo="Quién ve tus documentos">
            Los documentos que enviás para verificar tu identidad se usan sólo
            para eso, y los ve únicamente quien hace esa revisión. Qué datos se
            guardan, por cuánto tiempo, y cómo pedir su corrección o su
            eliminación está en la{' '}
            <Link to="/legal#privacidad" style={{ color: MORADO }}>política de privacidad</Link>.
          </Tarjeta>
          <Tarjeta icono={<MessageSquare size={18} color={MORADO} />} titulo="Si algo sale mal">
            Cada operación tiene un identificador propio que sirve para
            reclamar. Los motivos por los que procede o no procede una
            devolución, y sus plazos, están en las{' '}
            <Link to="/legal#reembolsos" style={{ color: MORADO }}>políticas de reembolso</Link>.
          </Tarjeta>
        </div>

        {/* ── Legal ────────────────────────────────────────────────────── */}
        <div style={{
          marginTop: 36, border: '1px solid #ececf3', borderRadius: 14,
          padding: 22, background: '#fafafe',
        }}>
          <h3 style={{ margin: '0 0 6px', fontSize: 16, fontWeight: 700 }}>Quién opera la plataforma</h3>
          {/*
            La identificación completa del operador —razón social, CNPJ y
            domicilio— vive en la ficha de empresa del documento legal, y no
            repetida en cada página pública. Repetirla en varios lugares tiene
            dos costos: expone los datos del titular en pantallas que no los
            necesitan, y obliga a acordarse de cambiarlos en todas cuando algo
            se actualiza. Acá se enlaza.
          */}
          <p style={{ margin: '0 0 14px', fontSize: 14, color: '#4b5563', lineHeight: 1.65 }}>
            La plataforma es operada por SAIPHA Servicios Digitais, empresa
            registrada en Brasil. Los datos completos del operador están en la{' '}
            <Link to="/legal#empresa" style={{ color: MORADO }}>información de la empresa</Link>.
            El tratamiento de datos personales se rige por la <i>Lei Geral de
            Proteção de Dados</i> (Lei n.º 13.709/2018).
          </p>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 14 }}>
            <Link to="/legal#privacidad" style={{ color: MORADO, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              Política de privacidad <ArrowRight size={14} />
            </Link>
            <Link to="/legal#terminos" style={{ color: MORADO, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              Términos y condiciones <ArrowRight size={14} />
            </Link>
            <Link to="/legal#cancelacion" style={{ color: MORADO, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              Cancelación de cuenta <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
