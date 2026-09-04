import { Link } from 'react-router-dom';
import {
  Wallet, Bitcoin, ShieldCheck, Clock, Smartphone, LayoutDashboard,
  ArrowRight, CheckCircle2, TrendingUp, QrCode, Lock, FileText, Zap,
} from 'lucide-react';
import Footer from '../components/Footer';

/**
 * Landing.jsx — Página pública de risappbr.com, para visitantes SIN sesión.
 *
 * REGLA DE NEGOCIO EXPLICITA
 *
 *   Esta página NO menciona remesas, transferencias internacionales, envíos
 *   transfronterizos ni cambio de dinero, y no muestra un cotizador que
 *   calcule cuánto recibe alguien en otra moneda. Todo se describe como
 *   SOLUCIONES DIGITALES, que es la línea principal de servicio. Los
 *   indicadores económicos generales sí se pueden mostrar, pero nunca como
 *   "tu tasa". El detalle de cada operación vive DESPUES del login.
 *
 *   Hay un test en el backend que falla si alguna de esas palabras aparece.
 *
 * QUE TIENE QUE LOGRAR EL DISEÑO
 *
 *   Quien entra acá está decidiendo si le confía su dinero a un desconocido.
 *   La página tiene que responder eso antes que nada, y se responde
 *   mostrando rigor, no adjetivos:
 *
 *     - Jerarquía tipográfica clara: una sola cosa importante por pantalla.
 *     - Afirmaciones verificables contra lo que el sistema hace. Nada de
 *       "el mejor" ni "sin papeleos": frases que se pueden auditar.
 *     - Los pasos reales para empezar, con su orden y su porqué. Un proceso
 *       explicado es un proceso que existe.
 *     - Enlaces visibles al marco legal y a cómo funciona. Esconderlos es
 *       lo que hace una plataforma que no quiere que la miren de cerca.
 *
 *   Los estados de foco y las transiciones van en una hoja de estilo local en
 *   vez de estilos en línea: `:hover` y `:focus-visible` no se pueden
 *   expresar con el atributo `style`, y sin foco visible la página no se
 *   puede recorrer con el teclado.
 */

const MORADO = '#5B4FE9';
const MORADO_OSCURO = '#3B3A9E';
const TINTA = '#111827';
const TEXTO = '#4b5563';
const SUAVE = '#6b7280';
const BORDE = '#eceaf6';

const ANCHO = 1100;

const SERVICIOS = [
  {
    icon: QrCode,
    color: '#16a34a',
    titulo: 'Recarga instantánea con PIX',
    desc: 'El saldo se acredita apenas se confirma el pago, sin intervención manual.',
  },
  {
    icon: Wallet,
    color: MORADO,
    titulo: 'Recargas digitales',
    desc: 'Distintos métodos de pago para acreditar saldo en tu cuenta.',
  },
  {
    icon: Bitcoin,
    color: '#f59e0b',
    titulo: 'Operaciones con Bitcoin',
    desc: 'Opera por la red Lightning, con confirmación casi inmediata.',
  },
  {
    icon: TrendingUp,
    color: '#2775CA',
    titulo: 'Créditos digitales USDT y USDC',
    desc: 'Convierte tus depósitos en créditos para usar dentro de la plataforma.',
  },
  {
    icon: LayoutDashboard,
    color: '#0891b2',
    titulo: 'Panel de control personal',
    desc: 'Tu historial completo y el estado de cada operación, en un solo lugar.',
  },
  {
    icon: Smartphone,
    color: '#7c3aed',
    titulo: 'Sin instalar nada',
    desc: 'Todo desde el navegador, en el teléfono o en la computadora.',
  },
];

// Afirmaciones que se pueden comprobar contra el sistema, no promesas.
const GARANTIAS = [
  {
    icon: Zap,
    titulo: 'Acreditación automática',
    desc: 'Las recargas se procesan solas al confirmarse el pago. Nadie las aprueba a mano.',
  },
  {
    icon: Lock,
    titulo: 'Cada operación, una sola vez',
    desc: 'El sistema impide que un mismo pago se acredite dos veces, aunque el aviso llegue repetido.',
  },
  {
    icon: FileText,
    titulo: 'Todo queda registrado',
    desc: 'Cada movimiento se asienta con fecha, hora y responsable, y queda disponible en tu historial.',
  },
];

const PASOS = [
  {
    n: '01',
    titulo: 'Crea tu cuenta',
    desc: 'Con tu correo electrónico. Verificas la dirección y ya puedes entrar.',
  },
  {
    n: '02',
    titulo: 'Verifica tu identidad',
    desc: 'Para operar por encima del cupo inicial. Es el paso que protege tu cuenta y la de los demás.',
  },
  {
    n: '03',
    titulo: 'Recarga y opera',
    desc: 'Eliges el método, confirmas el importe y el saldo queda disponible.',
  },
];

const ESTILOS = `
  .ris-a { transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease; }
  .ris-a:hover { transform: translateY(-2px); }
  .ris-cta:hover { box-shadow: 0 14px 30px rgba(91,79,233,.34); }
  .ris-card:hover { border-color: #d9d4f5; box-shadow: 0 6px 20px rgba(17,24,39,.06); }
  .ris-ghost:hover { border-color: #c9c3ee; }
  .ris-a:focus-visible, .ris-link:focus-visible {
    outline: 2px solid ${MORADO}; outline-offset: 3px; border-radius: 10px;
  }
  .ris-link { transition: color .15s ease; }
  .ris-link:hover { color: ${MORADO_OSCURO}; }
  @media (max-width: 640px) {
    .ris-hero-h1 { font-size: 34px !important; }
    .ris-sec-h2 { font-size: 24px !important; }
  }
`;

function Titulo({ eyebrow, children, sub, centrado = true }) {
  return (
    <div style={{
      textAlign: centrado ? 'center' : 'left',
      maxWidth: centrado ? 620 : undefined,
      margin: centrado ? '0 auto 40px' : '0 0 28px',
    }}
    >
      {eyebrow && (
        <p style={{
          margin: '0 0 10px', fontSize: 12, fontWeight: 700, color: MORADO,
          textTransform: 'uppercase', letterSpacing: '.09em',
        }}
        >
          {eyebrow}
        </p>
      )}
      <h2
        className="ris-sec-h2"
        style={{
          margin: 0, fontSize: 30, fontWeight: 800, color: TINTA,
          letterSpacing: '-.02em', lineHeight: 1.25,
        }}
      >
        {children}
      </h2>
      {sub && (
        <p style={{
          margin: '12px 0 0', fontSize: 16, color: SUAVE, lineHeight: 1.65,
        }}
        >
          {sub}
        </p>
      )}
    </div>
  );
}

export default function Landing() {
  const seccion = { padding: '76px 20px' };
  const contenedor = { maxWidth: ANCHO, margin: '0 auto' };

  return (
    <div style={{
      minHeight: '100vh', backgroundColor: '#fff',
      fontFamily: 'Inter, Helvetica, -apple-system, sans-serif',
    }}
    >
      <style>{ESTILOS}</style>

      {/* ── Encabezado ─────────────────────────────────────────────────── */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 20,
        backgroundColor: 'rgba(255,255,255,.88)', backdropFilter: 'blur(10px)',
        borderBottom: `1px solid ${BORDE}`, padding: '13px 20px',
      }}
      >
        <div style={{
          ...contenedor, display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', gap: 16,
        }}
        >
          <img src="/logo-ris.jpeg" alt="RIS App" style={{ height: 34, borderRadius: 8 }} />

          <nav style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Link
              to="/como-funciona"
              className="ris-link"
              style={{
                padding: '9px 12px', fontSize: 14, fontWeight: 600,
                color: SUAVE, textDecoration: 'none',
              }}
            >
              Cómo funciona
            </Link>
            <Link
              to="/login"
              className="ris-link"
              style={{
                padding: '9px 14px', fontSize: 14, fontWeight: 600,
                color: '#374151', textDecoration: 'none',
              }}
            >
              Iniciar sesión
            </Link>
            <Link
              to="/register"
              className="ris-a ris-cta"
              style={{
                padding: '10px 19px', borderRadius: 11, fontSize: 14, fontWeight: 700,
                color: '#fff', textDecoration: 'none',
                background: `linear-gradient(135deg, ${MORADO} 0%, ${MORADO_OSCURO} 100%)`,
              }}
            >
              Crear cuenta
            </Link>
          </nav>
        </div>
      </header>

      {/* ── Portada ────────────────────────────────────────────────────── */}
      <section style={{
        padding: '86px 20px 70px',
        background: 'radial-gradient(ellipse 80% 60% at 50% -10%, #efecff 0%, #ffffff 62%)',
      }}
      >
        <div style={{ maxWidth: 760, margin: '0 auto', textAlign: 'center' }}>
          <p style={{
            display: 'inline-block', margin: '0 0 22px', padding: '6px 14px',
            borderRadius: 999, background: '#fff', border: `1px solid ${BORDE}`,
            fontSize: 12.5, fontWeight: 600, color: MORADO, letterSpacing: '.02em',
          }}
          >
            Soluciones digitales
          </p>

          <h1
            className="ris-hero-h1"
            style={{
              fontSize: 50, fontWeight: 800, color: TINTA, lineHeight: 1.1,
              margin: '0 0 20px', letterSpacing: '-.035em',
            }}
          >
            Una cuenta seria para tus{' '}
            <span style={{ color: MORADO }}>operaciones digitales</span>
          </h1>

          <p style={{
            fontSize: 18, color: TEXTO, lineHeight: 1.65, margin: '0 auto 32px',
            maxWidth: 560,
          }}
          >
            Recarga tu saldo, opera con Bitcoin y activa créditos digitales USDT
            y USDC. Cada movimiento se procesa de forma automática y queda
            registrado.
          </p>

          <div style={{
            display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center',
          }}
          >
            <Link
              to="/register"
              className="ris-a ris-cta"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 9,
                padding: '16px 28px', borderRadius: 13, fontSize: 15.5,
                fontWeight: 700, color: '#fff', textDecoration: 'none',
                background: `linear-gradient(135deg, ${MORADO} 0%, ${MORADO_OSCURO} 100%)`,
                boxShadow: '0 10px 24px rgba(91,79,233,.26)',
              }}
            >
              Crear cuenta gratis <ArrowRight size={17} />
            </Link>
            <Link
              to="/login"
              className="ris-a ris-ghost"
              style={{
                display: 'inline-flex', alignItems: 'center',
                padding: '16px 28px', borderRadius: 13, fontSize: 15.5,
                fontWeight: 700, color: '#374151', textDecoration: 'none',
                border: `1.5px solid ${BORDE}`, background: '#fff',
              }}
            >
              Ya tengo cuenta
            </Link>
          </div>

          {/* Franja de confianza: fina, no tres tarjetas grandes. */}
          <div style={{
            display: 'flex', flexWrap: 'wrap', justifyContent: 'center',
            gap: '10px 26px', marginTop: 38,
          }}
          >
            {/*
              El icono llega ya renderizado y no como componente: el linter de
              este repositorio no cuenta el uso en JSX de un elemento
              desestructurado, y pasarlo así evita la excepción sin apagar la
              regla. Mismo criterio que en ComoFunciona.jsx.
            */}
            {[
              { texto: 'Acreditación al instante', icono: <Clock size={15} color={MORADO} /> },
              { texto: 'Identidad verificada', icono: <ShieldCheck size={15} color={MORADO} /> },
              { texto: 'Desde el navegador', icono: <Smartphone size={15} color={MORADO} /> },
            ].map((it) => (
              <span
                key={it.texto}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 7,
                  fontSize: 13.5, color: SUAVE, fontWeight: 500,
                }}
              >
                {it.icono}
                {it.texto}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── Cómo se empieza ────────────────────────────────────────────── */}
      <section style={{ ...seccion, paddingTop: 40, background: '#fff' }}>
        <div style={contenedor}>
          <Titulo
            eyebrow="Empezar toma minutos"
            sub="Tres pasos, en este orden. El segundo es el que protege tu cuenta."
          >
            Cómo se empieza
          </Titulo>

          <div style={{
            display: 'grid', gap: 18,
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          }}
          >
            {PASOS.map((s) => (
              <div
                key={s.n}
                style={{
                  position: 'relative', padding: '26px 24px 24px',
                  borderRadius: 16, border: `1px solid ${BORDE}`, background: '#fff',
                }}
              >
                <span style={{
                  fontSize: 30, fontWeight: 800, color: '#e6e2f8',
                  letterSpacing: '-.03em', lineHeight: 1,
                }}
                >
                  {s.n}
                </span>
                <p style={{
                  margin: '14px 0 7px', fontSize: 16.5, fontWeight: 700, color: TINTA,
                }}
                >
                  {s.titulo}
                </p>
                <p style={{ margin: 0, fontSize: 14, color: SUAVE, lineHeight: 1.6 }}>
                  {s.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Servicios ──────────────────────────────────────────────────── */}
      <section style={{ ...seccion, background: '#fafafc' }}>
        <div style={contenedor}>
          <Titulo
            eyebrow="Qué puedes hacer"
            sub="Una sola cuenta para todas tus operaciones dentro de la plataforma."
          >
            Servicios disponibles
          </Titulo>

          <div style={{
            display: 'grid', gap: 18,
            gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
          }}
          >
            {SERVICIOS.map((f) => (
              <Link
                key={f.titulo}
                to="/register"
                className="ris-a ris-card"
                style={{
                  display: 'block', padding: 26, borderRadius: 16,
                  backgroundColor: '#fff', border: `1px solid ${BORDE}`,
                  textDecoration: 'none',
                }}
              >
                <div style={{
                  width: 44, height: 44, borderRadius: 12,
                  backgroundColor: `${f.color}16`, display: 'flex',
                  alignItems: 'center', justifyContent: 'center', marginBottom: 16,
                }}
                >
                  <f.icon size={21} color={f.color} />
                </div>
                <p style={{
                  margin: '0 0 7px', fontWeight: 700, fontSize: 16, color: TINTA,
                }}
                >
                  {f.titulo}
                </p>
                <p style={{ margin: 0, fontSize: 14, color: SUAVE, lineHeight: 1.6 }}>
                  {f.desc}
                </p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* ── Cómo trabajamos ────────────────────────────────────────────── */}
      <section style={seccion}>
        <div style={{
          ...contenedor, display: 'flex', gap: 56, flexWrap: 'wrap',
          alignItems: 'flex-start',
        }}
        >
          <div style={{ flex: '1 1 300px', minWidth: 280 }}>
            <Titulo eyebrow="Cómo trabajamos" centrado={false}>
              Lo que hace el sistema, no lo que prometemos
            </Titulo>
            <p style={{
              fontSize: 15.5, color: TEXTO, lineHeight: 1.7, margin: '0 0 24px',
            }}
            >
              Todo lo que está a la derecha se puede comprobar desde tu propia
              cuenta. No hay letra chica: las reglas completas están publicadas.
            </p>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <Link
                to="/como-funciona"
                className="ris-a ris-ghost"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 7,
                  padding: '11px 17px', borderRadius: 11, fontSize: 14,
                  fontWeight: 600, color: MORADO, textDecoration: 'none',
                  border: `1.5px solid ${BORDE}`,
                }}
              >
                Cómo funciona <ArrowRight size={15} />
              </Link>
              <Link
                to="/legal"
                className="ris-a ris-ghost"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 7,
                  padding: '11px 17px', borderRadius: 11, fontSize: 14,
                  fontWeight: 600, color: '#374151', textDecoration: 'none',
                  border: `1.5px solid ${BORDE}`,
                }}
              >
                Marco legal
              </Link>
            </div>
          </div>

          <div style={{
            flex: '1 1 340px', minWidth: 300,
            display: 'flex', flexDirection: 'column', gap: 14,
          }}
          >
            {GARANTIAS.map((g) => (
              <div
                key={g.titulo}
                style={{
                  display: 'flex', gap: 15, padding: '20px 22px', borderRadius: 15,
                  background: '#fafafc', border: `1px solid ${BORDE}`,
                }}
              >
                <div style={{
                  width: 40, height: 40, borderRadius: 11, background: '#fff',
                  border: `1px solid ${BORDE}`, display: 'flex',
                  alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}
                >
                  <g.icon size={19} color={MORADO} />
                </div>
                <div>
                  <p style={{
                    margin: '0 0 5px', fontWeight: 700, fontSize: 15, color: TINTA,
                  }}
                  >
                    {g.titulo}
                  </p>
                  <p style={{ margin: 0, fontSize: 13.5, color: SUAVE, lineHeight: 1.6 }}>
                    {g.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Seguridad ──────────────────────────────────────────────────── */}
      <section style={{ ...seccion, background: '#fafafc' }}>
        <div style={{
          ...contenedor, display: 'flex', gap: 56, alignItems: 'center',
          flexWrap: 'wrap',
        }}
        >
          <div style={{ flex: '1 1 320px', minWidth: 280 }}>
            <div style={{
              width: 52, height: 52, borderRadius: 15,
              background: `linear-gradient(135deg, ${MORADO} 0%, ${MORADO_OSCURO} 100%)`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: 20,
            }}
            >
              <ShieldCheck size={25} color="#fff" />
            </div>
            <h3 style={{
              fontSize: 27, fontWeight: 800, color: TINTA, margin: '0 0 14px',
              letterSpacing: '-.02em', lineHeight: 1.25,
            }}
            >
              Seguridad en cada operación
            </h3>
            <p style={{ fontSize: 15.5, color: TEXTO, lineHeight: 1.7, margin: 0 }}>
              Tu cuenta está protegida por verificación en dos pasos, y el
              personal con acceso administrativo la tiene obligatoria. Los
              distintos tipos de créditos se gestionan de forma independiente
              dentro de la plataforma.
            </p>
          </div>

          <div style={{
            flex: '1 1 320px', minWidth: 280,
            display: 'flex', flexDirection: 'column', gap: 13,
          }}
          >
            {[
              'Verificación en dos pasos disponible para tu cuenta.',
              'Verificación de identidad antes de operar montos mayores.',
              'Los saldos se calculan con precisión exacta, sin redondeos ocultos.',
              'Las credenciales se guardan cifradas, nunca en texto plano.',
            ].map((linea) => (
              <div key={linea} style={{ display: 'flex', gap: 11, alignItems: 'flex-start' }}>
                <CheckCircle2
                  size={18}
                  color="#16a34a"
                  style={{ flexShrink: 0, marginTop: 2 }}
                />
                <p style={{ margin: 0, fontSize: 14.5, color: '#374151', lineHeight: 1.6 }}>
                  {linea}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Cierre ─────────────────────────────────────────────────────── */}
      <section style={{ padding: '70px 20px 80px' }}>
        <div style={{
          ...contenedor, borderRadius: 22, padding: '56px 32px', textAlign: 'center',
          background: `linear-gradient(135deg, ${MORADO} 0%, ${MORADO_OSCURO} 100%)`,
        }}
        >
          <h2 style={{
            fontSize: 30, fontWeight: 800, color: '#fff', margin: '0 0 12px',
            letterSpacing: '-.02em',
          }}
          >
            Crea tu cuenta y empieza a operar
          </h2>
          <p style={{
            fontSize: 16, color: 'rgba(255,255,255,.88)', margin: '0 auto 28px',
            maxWidth: 460, lineHeight: 1.65,
          }}
          >
            El registro toma un minuto. Los requisitos y los límites están
            publicados antes de que abras la cuenta.
          </p>
          <Link
            to="/register"
            className="ris-a"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 9,
              padding: '16px 30px', borderRadius: 13, fontSize: 15.5,
              fontWeight: 700, color: MORADO, backgroundColor: '#fff',
              textDecoration: 'none',
            }}
          >
            Crear cuenta gratis <ArrowRight size={17} />
          </Link>
        </div>
      </section>

      <Footer />
    </div>
  );
}
