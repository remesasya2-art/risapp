/**
 * ComoFunciona.jsx — Página pública de transparencia operativa.
 *
 * POR QUE EXISTE
 *
 *   Quien evalúa esta plataforma —un usuario que decide si confía, o una
 *   revisión de cumplimiento -- mira primero lo que está publicado: quién
 *   opera, con qué límites, qué verificación pide, y qué queda registrado.
 *   Eso estaba repartido entre la landing y la página legal, o directamente no
 *   estaba.
 *
 * LA REGLA QUE RESPETA
 *
 *   `Landing.jsx` deja escrita una regla de negocio explícita: las páginas
 *   públicas NO mencionan remesas ni transferencias internacionales; todo se
 *   describe como "operaciones digitales" de forma genérica. Esta página se
 *   escribió dentro de esa regla a propósito.
 *
 * LOS NUMEROS SON VIVOS, NO ESCRITOS A MANO
 *
 *   Los límites y el cupo salen de `GET /api/limits`, que es el MISMO módulo
 *   que el servidor usa para validar. Escribirlos acá a mano significaría que
 *   el día que alguien cambie una constante, esta página seguiría publicando
 *   el número viejo — y nadie se enteraría, porque no falla nada. Hay tests en
 *   el backend que comprueban que lo publicado y lo que se hace cumplir son el
 *   mismo valor.
 *
 *   Si la consulta falla, NO se inventa un número: se dice que no se pudieron
 *   cargar. Un límite equivocado en una página pública es una promesa que no
 *   se puede cumplir.
 *
 * LO QUE ESTA PAGINA NO DICE
 *
 *   Una página pública puede prometer un RESULTADO; no describe el MECANISMO
 *   que lo garantiza. La primera versión de "Qué queda registrado" enumeraba
 *   los controles internos: que el acceso administrativo pide un segundo
 *   factor, que la comprobación de saldos es periódica, y la lista completa de
 *   lo que un administrador puede hacer —aprobar una verificación, ajustar un
 *   saldo, cambiar una tasa, modificar permisos—.
 *
 *   Eso no le sirve a quien está decidiendo si confía, y sí le sirve a quien
 *   está mirando por dónde entrar: le dice qué cuenta vale la pena tomar, qué
 *   defensa va a encontrar y —lo peor— qué tiene que imitar una página de
 *   phishing para que el engaño funcione. "Periódica", además, es la palabra
 *   que dice que hay una ventana.
 *
 *   El detalle no se borró: vive en `docs/dossier-tecnico-de-seguridad.md`
 *   (§3.3 segundo factor, §4.3 el personal no opera a título personal, §5
 *   integridad del dinero, §6 trazabilidad), que es interno y se entrega bajo
 *   acuerdo a quien tenga que auditarlo. Acá quedan las promesas: que todo
 *   movimiento deja rastro, que toda intervención del equipo queda asentada, y
 *   que el usuario puede pedir ese rastro.
 *
 *   `test_lenguaje_de_las_paginas_publicas.py` sostiene la regla.
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
            tiene, comprobante de CPF y una selfie. Cada envío se revisa uno por
            uno. Si algo no se lee bien, se rechaza indicando el motivo y se
            puede volver a enviar.
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
