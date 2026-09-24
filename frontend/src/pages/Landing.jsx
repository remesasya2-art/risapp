import { Link } from 'react-router-dom';
import {
  Wallet, Bitcoin, ShieldCheck, Clock, Smartphone, LayoutDashboard,
  ArrowRight, CheckCircle2, TrendingUp, QrCode, Lock, FileText, Zap, Sparkles,
  Plus, History, MessageCircle, User,
} from 'lucide-react';
import Footer from '../components/Footer';
import SelectorDeApariencia from '../components/tema/SelectorDeApariencia';
import useCripto from '../hooks/useCripto';

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
 *   Vale también para el teléfono de muestra de la portada: enseña un saldo
 *   y recargas, y NO un envío ni su equivalente en otra moneda. Una pantalla
 *   de ejemplo que muestra un envío es un envío anunciado.
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
 * EL ESTILO
 *
 *   El lenguaje visual de Apple: tarjetas de vidrio sobre una pared de
 *   colores, tipografía grande, listas agrupadas. Los colores no se escriben
 *   acá: son los nombres de index.css (`var(--t-texto)`), que cambian solos
 *   entre claro y oscuro. Escribir un color a mano en esta página lo deja
 *   igual en los dos modos, y en uno de los dos se va a leer mal.
 *
 *   Los estados de foco y las transiciones van en una hoja de estilo local en
 *   vez de estilos en línea: `:hover` y `:focus-visible` no se pueden
 *   expresar con el atributo `style`, y sin foco visible la página no se
 *   puede recorrer con el teclado.
 */

const ANCHO = 1120;

const SERVICIOS = [
  {
    icon: QrCode,
    color: '#28b463',
    titulo: 'Recarga instantánea con PIX',
    desc: 'El saldo se acredita apenas se confirma el pago, sin intervención manual.',
  },
  {
    icon: Wallet,
    color: '#5b4fe9',
    titulo: 'Recargas digitales',
    desc: 'Distintos métodos de pago para acreditar saldo en tu cuenta.',
  },
  // LAS DOS DE CRIPTO VAN MARCADAS, NO BORRADAS.
  //
  //   `cripto: true` es lo que las saca de la lista cuando la vía está
  //   apagada, y lo que las devuelve el día que se vuelva a prender desde el
  //   panel. Marcarlas es mejor que una lista aparte de «las que se esconden»:
  //   esa lista se desactualiza el día que alguien agregue una tarjeta nueva.
  {
    icon: Bitcoin,
    color: '#f59e0b',
    cripto: true,
    titulo: 'Operaciones con Bitcoin',
    desc: 'Opera por la red Lightning, con confirmación casi inmediata.',
  },
  {
    icon: TrendingUp,
    color: '#2775CA',
    cripto: true,
    titulo: 'Créditos digitales USDT y USDC',
    desc: 'Convierte tus depósitos en créditos para usar dentro de la plataforma.',
  },
  {
    icon: LayoutDashboard,
    color: '#0a84ff',
    titulo: 'Panel de control personal',
    desc: 'Tu historial completo y el estado de cada operación, en un solo lugar.',
  },
  {
    icon: Smartphone,
    color: '#f28c28',
    titulo: 'Sin instalar nada',
    desc: 'Todo desde el navegador, en el teléfono o en la computadora.',
  },
];

// Afirmaciones que se pueden comprobar contra el sistema, no promesas.
const GARANTIAS = [
  {
    icon: Zap,
    color: '#ff9f0a',
    titulo: 'Acreditación automática',
    desc: 'Las recargas se procesan solas al confirmarse el pago. Nadie las aprueba a mano.',
  },
  {
    icon: Lock,
    color: '#5b4fe9',
    titulo: 'Cada operación, una sola vez',
    desc: 'El sistema impide que un mismo pago se acredite dos veces, aunque el aviso llegue repetido.',
  },
  {
    icon: FileText,
    color: '#8e8e93',
    titulo: 'Todo queda registrado',
    desc: 'Cada movimiento se asienta con fecha, hora y responsable, y queda disponible en tu historial.',
  },
];

const PASOS = [
  {
    n: '1',
    titulo: 'Crea tu cuenta',
    desc: 'Con tu correo electrónico. Verificas la dirección y ya puedes entrar.',
  },
  {
    n: '2',
    titulo: 'Verifica tu identidad',
    desc: 'Para operar por encima del cupo inicial. Es el paso que protege tu cuenta y la de los demás.',
  },
  {
    n: '3',
    titulo: 'Recarga y opera',
    desc: 'Eliges el método, confirmas el importe y el saldo queda disponible.',
  },
];

const SEGURIDAD = [
  'Verificación en dos pasos disponible para tu cuenta.',
  'Verificación de identidad antes de operar montos mayores.',
  'Los saldos se calculan con precisión exacta, sin redondeos ocultos.',
  'Las credenciales se guardan cifradas, nunca en texto plano.',
];

const ESTILOS = `
  .p-nav-links a { color: var(--t-texto-2); text-decoration: none; font-size: 14px; transition: color .15s ease; }
  .p-nav-links a:hover { color: var(--t-texto); }
  .p-tarjeta { transition: transform .18s ease, box-shadow .18s ease; }
  .p-tarjeta:hover { transform: translateY(-3px); }
  .p-heroe { display: grid; grid-template-columns: 1fr 420px; gap: 48px; align-items: center; }
  .p-pasos { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
  .p-servicios { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 20px; }
  .p-dos { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  @media (max-width: 960px) {
    .p-heroe { grid-template-columns: 1fr; }
    .p-telefono { display: none !important; }
    .p-dos { grid-template-columns: 1fr; }
  }
  @media (max-width: 860px) {
    .p-nav-links { display: none !important; }
    .p-pasos { grid-template-columns: 1fr; }
  }
  @media (max-width: 640px) {
    .p-h1 { font-size: 42px !important; }
    .p-h2 { font-size: 32px !important; }
    .p-cta-h2 { font-size: 32px !important; }
    .p-acciones { flex-direction: column; align-items: stretch !important; }
    .p-seccion { padding-top: 48px !important; padding-bottom: 48px !important; }
  }
  @media (max-width: 440px) {
    .p-marca-texto { display: none; }
    .p-nav-entrar { padding: 0 8px !important; }
  }
`;

function Titulo({ eyebrow, children, sub }) {
  return (
    <div style={{ textAlign: 'center', maxWidth: 640, margin: '0 auto 44px' }}>
      {eyebrow && <p className="t-eyebrow">{eyebrow}</p>}
      <h2
        className="p-h2"
        style={{
          margin: '10px 0 0', fontSize: 46, fontWeight: 700, color: 'var(--t-texto)',
          letterSpacing: '-.04em', lineHeight: 1.06,
        }}
      >
        {children}
      </h2>
      {sub && (
        <p style={{ margin: '14px 0 0', fontSize: 18, color: 'var(--t-texto-2)', lineHeight: 1.5 }}>
          {sub}
        </p>
      )}
    </div>
  );
}

function Cuadro({ color, children, tam = 32, radio = 9 }) {
  return (
    <div style={{
      width: tam, height: tam, borderRadius: radio, flexShrink: 0,
      display: 'grid', placeItems: 'center', color: '#fff',
      background: `linear-gradient(180deg, ${color}cc, ${color})`,
    }}
    >
      {children}
    </div>
  );
}

// Una pantalla de la app en miniatura, para que quien llega vea el producto
// antes de registrarse. Es decorativa: el lector de pantalla la salta
// (`aria-hidden`), porque leerle «Hola, Ana» a alguien que no es Ana confunde.
function TelefonoDeMuestra() {
  const accion = (icono, texto, principal) => (
    <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--t-texto-2)' }}>
      <span style={{
        width: 46, height: 46, borderRadius: '50%', display: 'grid', placeItems: 'center',
        background: principal ? 'var(--t-acento)' : 'var(--t-campo)',
        color: principal ? '#fff' : 'var(--t-acento)',
      }}
      >
        {icono}
      </span>
      {texto}
    </span>
  );
  const fila = (color, icono, titulo, sub, monto) => (
    <div className="t-fila" style={{ padding: '11px 12px', gap: 10 }}>
      <Cuadro color={color} tam={28} radio={8}>{icono}</Cuadro>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{titulo}</div>
        <div style={{ fontSize: 11, color: 'var(--t-texto-2)' }}>{sub}</div>
      </div>
      {monto && <div style={{ marginLeft: 'auto', fontSize: 13, fontWeight: 600, color: 'var(--t-verde)' }}>{monto}</div>}
    </div>
  );
  const aviso = (estilo, color, icono, titulo, sub) => (
    <div
      className="t-vidrio"
      style={{
        position: 'absolute', zIndex: 2, borderRadius: 20, padding: '12px 16px',
        display: 'flex', gap: 12, alignItems: 'center', ...estilo,
      }}
    >
      <Cuadro color={color} tam={32} radio={16}>{icono}</Cuadro>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{titulo}</div>
        <div style={{ fontSize: 12, color: 'var(--t-texto-2)' }}>{sub}</div>
      </div>
    </div>
  );

  return (
    <div className="p-telefono" aria-hidden="true" style={{ position: 'relative', height: 560 }}>
      <div
        className="t-vidrio"
        style={{
          position: 'absolute', right: 20, top: 0, width: 300, height: 560,
          borderRadius: 52, padding: 14, transform: 'rotate(-4deg)',
        }}
      >
        <div style={{
          height: '100%', borderRadius: 40, background: 'var(--t-fondo)', overflow: 'hidden',
          position: 'relative', padding: '48px 16px 0',
        }}
        >
          <div style={{
            position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)',
            width: 90, height: 26, borderRadius: 20, background: '#000',
          }}
          />
          <div style={{ fontSize: 13, color: 'var(--t-texto-2)' }}>Buenos días</div>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '-.03em', margin: '6px 0 14px' }}>Hola, Ana</div>
          <div style={{
            borderRadius: 22, padding: 18, color: '#fff',
            background: 'linear-gradient(135deg, #6d62ff, #8b5cf6 60%, #f28c28)',
          }}
          >
            <div style={{ fontSize: 12, opacity: 0.85 }}>Saldo disponible</div>
            <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-.03em', marginTop: 4 }}>RI$ 250,00</div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', margin: '16px 4px' }}>
            {accion(<Plus size={20} />, 'Recargar', true)}
            {accion(<History size={19} />, 'Historial')}
            {accion(<MessageCircle size={19} />, 'Ayuda')}
            {accion(<User size={19} />, 'Perfil')}
          </div>
          <div className="t-grupo">
            {fila('#34c759', <Plus size={15} />, 'Recarga PIX', 'Hoy · Acreditada', '+ 100,00')}
            {fila('#34c759', <Plus size={15} />, 'Recarga PIX', 'Ayer · Acreditada', '+ 50,00')}
            {fila('#5b4fe9', <ShieldCheck size={15} />, 'Identidad', 'Lun · Verificada')}
          </div>
        </div>
      </div>
      {aviso({ left: -30, top: -6 }, '#34c759', <CheckCircle2 size={17} />, 'Recarga acreditada', 'RI$ 100,00 · hace 4 s')}
      {aviso({ left: -100, bottom: 90 }, '#5b4fe9', <ShieldCheck size={17} />, 'Identidad verificada', 'Tu cuenta está protegida')}
    </div>
  );
}

export default function Landing() {
  // LA PORTADA MIRA `deposito`, NO `visible`.
  //
  //   Quien llega acá no tiene cuenta, así que no puede tener saldo cripto que
  //   sacar. Ofrecerle depositar en una vía que sólo acepta retiros sería
  //   prometerle algo que el servidor le va a negar con un 503 después de
  //   registrarse. `/limits` es pública, así que esto no pide sesión.
  const { deposito: ofreceCripto } = useCripto();
  const seccion = { position: 'relative', zIndex: 1, maxWidth: ANCHO, margin: '0 auto', padding: '72px 20px' };

  return (
    <div className="con-tema" style={{ minHeight: '100vh', position: 'relative', overflow: 'hidden' }}>
      <style>{ESTILOS}</style>

      <div className="t-pared" aria-hidden="true">
        <i style={{ width: 620, height: 620, left: -140, top: -160, background: 'var(--t-mancha-1)' }} />
        <i style={{ width: 520, height: 520, right: -80, top: 40, background: 'var(--t-mancha-2)' }} />
        <i style={{ width: 560, height: 560, right: '22%', top: 420, background: 'var(--t-mancha-3)' }} />
        <i style={{ width: 600, height: 600, left: -200, top: 1500, background: 'var(--t-mancha-4)' }} />
        <i style={{ width: 520, height: 520, right: -160, top: 1900, background: 'var(--t-mancha-1)' }} />
        <i style={{ width: 520, height: 520, left: '25%', top: 2700, background: 'var(--t-mancha-3)' }} />
      </div>

      {/* ── Encabezado ─────────────────────────────────────────────────── */}
      <header style={{ position: 'sticky', top: 12, zIndex: 20, padding: '0 16px', marginTop: 12 }}>
        <div
          className="t-vidrio"
          style={{
            maxWidth: ANCHO, margin: '0 auto', height: 60, borderRadius: 999,
            display: 'flex', alignItems: 'center', gap: 10, padding: '0 10px 0 12px',
          }}
        >
          <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none', color: 'var(--t-texto)' }}>
            <img src="/logo-ris.png" alt="RISApp" width={34} height={34} className="t-logo" style={{ borderRadius: 9, display: 'block' }} />
            <span className="p-marca-texto" style={{ fontWeight: 700, fontSize: 17 }}>RISApp</span>
          </Link>

          <nav className="p-nav-links" style={{ display: 'flex', gap: 26, marginLeft: 40 }}>
            <a href="#como-se-empieza">Cómo funciona</a>
            <a href="#servicios">Servicios</a>
            <a href="#seguridad">Seguridad</a>
            <Link to="/legal">Marco legal</Link>
          </nav>

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
            <SelectorDeApariencia />
            <Link
              to="/login"
              className="p-nav-entrar"
              style={{ padding: '0 12px', fontSize: 14, fontWeight: 600, color: 'var(--t-texto)', textDecoration: 'none' }}
            >
              Iniciar sesión
            </Link>
            <Link to="/register" className="t-boton t-primario" style={{ minHeight: 40, fontSize: 14, padding: '0 18px' }}>
              Crear cuenta
            </Link>
          </div>
        </div>
      </header>

      {/* ── Portada ────────────────────────────────────────────────────── */}
      <section className="p-seccion" style={{ ...seccion, paddingTop: 80, paddingBottom: 88 }}>
        <div className="p-heroe">
          <div>
            <span className="t-chip t-vidrio t-vidrio-plano">
              <Sparkles size={14} style={{ color: 'var(--t-acento)' }} />
              Soluciones digitales
            </span>

            <h1
              className="p-h1"
              style={{
                fontSize: 66, fontWeight: 700, lineHeight: 1.03, letterSpacing: '-.045em',
                margin: '18px 0 22px', color: 'var(--t-texto)',
              }}
            >
              Una cuenta seria para tus{' '}
              <span className="t-degradado">operaciones digitales.</span>
            </h1>

            <p style={{ fontSize: 20, lineHeight: 1.5, color: 'var(--t-texto-2)', maxWidth: 560, margin: 0 }}>
              {ofreceCripto
                ? ('Recarga tu saldo, opera con Bitcoin y activa créditos '
                   + 'digitales USDT y USDC. Cada movimiento se procesa de forma '
                   + 'automática y queda registrado.')
                : ('Recarga tu saldo con PIX y opera desde tu cuenta. Cada '
                   + 'movimiento se procesa de forma automática y queda '
                   + 'registrado.')}
            </p>

            <div className="p-acciones" style={{ display: 'flex', gap: 12, margin: '32px 0 24px', alignItems: 'center' }}>
              <Link to="/register" className="t-boton t-primario" style={{ minHeight: 54, fontSize: 17, padding: '0 30px' }}>
                Crear cuenta gratis <ArrowRight size={18} />
              </Link>
              <Link to="/login" className="t-boton t-secundario t-vidrio t-vidrio-plano" style={{ minHeight: 54, fontSize: 17, padding: '0 30px' }}>
                Ya tengo cuenta
              </Link>
            </div>

            {/*
              El icono llega ya renderizado y no como componente: el linter de
              este repositorio no cuenta el uso en JSX de un elemento
              desestructurado, y pasarlo así evita la excepción sin apagar la
              regla. Mismo criterio que en ComoFunciona.jsx.
            */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {[
                { texto: 'Acreditación al instante', icono: <Clock size={15} /> },
                { texto: 'Identidad verificada', icono: <ShieldCheck size={15} /> },
                { texto: 'Desde el navegador', icono: <Smartphone size={15} /> },
              ].map((it) => (
                <span key={it.texto} className="t-chip t-vidrio t-vidrio-plano">
                  <span style={{ color: 'var(--t-acento)', display: 'grid' }}>{it.icono}</span>
                  {it.texto}
                </span>
              ))}
            </div>
          </div>

          <TelefonoDeMuestra />
        </div>
      </section>

      {/* ── Cómo se empieza ────────────────────────────────────────────── */}
      <section id="como-se-empieza" className="p-seccion" style={seccion}>
        <Titulo
          eyebrow="Empezar toma minutos"
          sub="Tres pasos, en este orden. El segundo es el que protege tu cuenta."
        >
          Cómo se empieza.
        </Titulo>
        <div className="p-pasos">
          {PASOS.map((s) => (
            <div key={s.n} className="t-vidrio" style={{ borderRadius: 28, padding: 30 }}>
              <div className="t-degradado" style={{ fontSize: 56, fontWeight: 700, letterSpacing: '-.05em', lineHeight: 1 }}>
                {s.n}
              </div>
              <p style={{ fontSize: 21, fontWeight: 700, letterSpacing: '-.02em', margin: '22px 0 8px' }}>
                {s.titulo}
              </p>
              <p style={{ margin: 0, fontSize: 15, color: 'var(--t-texto-2)', lineHeight: 1.5 }}>
                {s.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Servicios ──────────────────────────────────────────────────── */}
      <section id="servicios" className="p-seccion" style={seccion}>
        <Titulo
          eyebrow="Qué puedes hacer"
          sub="Una sola cuenta para todas tus operaciones dentro de la plataforma."
        >
          Servicios disponibles.
        </Titulo>
        <div className="p-servicios">
          {SERVICIOS.filter((f) => ofreceCripto || !f.cripto).map((f) => (
            <Link
              key={f.titulo}
              to="/register"
              className="t-vidrio p-tarjeta"
              style={{ display: 'block', borderRadius: 28, padding: 26, textDecoration: 'none', color: 'var(--t-texto)' }}
            >
              <Cuadro color={f.color} tam={52} radio={14}>
                <f.icon size={24} color="#fff" />
              </Cuadro>
              <p style={{ margin: '22px 0 8px', fontWeight: 700, fontSize: 18, letterSpacing: '-.02em' }}>
                {f.titulo}
              </p>
              <p style={{ margin: 0, fontSize: 14, color: 'var(--t-texto-2)', lineHeight: 1.5 }}>
                {f.desc}
              </p>
            </Link>
          ))}
        </div>
      </section>

      {/* ── Cómo trabajamos y seguridad ────────────────────────────────── */}
      <section id="seguridad" className="p-seccion" style={seccion}>
        <div className="p-dos">
          <div className="t-vidrio" style={{ borderRadius: 32, padding: 34 }}>
            <p className="t-eyebrow">Cómo trabajamos</p>
            <h3 style={{ fontSize: 32, fontWeight: 700, letterSpacing: '-.035em', lineHeight: 1.1, margin: '8px 0 12px' }}>
              Lo que hace el sistema, no lo que prometemos.
            </h3>
            <p style={{ fontSize: 16, color: 'var(--t-texto-2)', lineHeight: 1.5, margin: '0 0 24px' }}>
              Todo lo que está acá se puede comprobar desde tu propia cuenta. No
              hay letra chica: las reglas completas están publicadas.
            </p>
            <div className="t-grupo">
              {GARANTIAS.map((g) => (
                <div key={g.titulo} className="t-fila">
                  <Cuadro color={g.color}><g.icon size={17} color="#fff" /></Cuadro>
                  <div>
                    <p style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>{g.titulo}</p>
                    <p style={{ margin: '2px 0 0', fontSize: 13, color: 'var(--t-texto-2)', lineHeight: 1.4 }}>{g.desc}</p>
                  </div>
                </div>
              ))}
            </div>
            <Link to="/legal" className="t-boton t-secundario t-vidrio t-vidrio-plano" style={{ marginTop: 20, minHeight: 44, fontSize: 15 }}>
              Marco legal
            </Link>
          </div>

          <div className="t-vidrio" style={{ borderRadius: 32, padding: 34 }}>
            <p className="t-eyebrow">Seguridad</p>
            <h3 style={{ fontSize: 32, fontWeight: 700, letterSpacing: '-.035em', lineHeight: 1.1, margin: '8px 0 12px' }}>
              Seguridad en cada operación.
            </h3>
            <p style={{ fontSize: 16, color: 'var(--t-texto-2)', lineHeight: 1.5, margin: '0 0 24px' }}>
              Tu cuenta puede protegerse con verificación en dos pasos, y la
              identidad se verifica antes de operar montos mayores. Los
              distintos tipos de créditos se gestionan de forma independiente
              dentro de la plataforma.
            </p>
            <div className="t-grupo">
              {SEGURIDAD.map((linea) => (
                <div key={linea} className="t-fila">
                  <CheckCircle2 size={22} style={{ color: 'var(--t-verde)', flexShrink: 0 }} />
                  <p style={{ margin: 0, fontSize: 15, lineHeight: 1.4 }}>{linea}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Cierre ─────────────────────────────────────────────────────── */}
      <section className="p-seccion" style={{ ...seccion, paddingTop: 40 }}>
        <div style={{
          borderRadius: 40, padding: '72px 32px', textAlign: 'center', color: '#fff',
          background: 'linear-gradient(135deg, #5144e0 0%, #7c5cf5 55%, #f28c28 130%)',
        }}
        >
          <h2 className="p-cta-h2" style={{ fontSize: 50, letterSpacing: '-.045em', lineHeight: 1.06, margin: 0 }}>
            Crea tu cuenta y empieza a operar.
          </h2>
          <p style={{ fontSize: 19, opacity: 0.9, margin: '16px auto 32px', maxWidth: 560, lineHeight: 1.45 }}>
            El registro toma un minuto. Los requisitos y los límites están
            publicados antes de que abras la cuenta.
          </p>
          <Link
            to="/register"
            className="t-boton"
            style={{ background: 'rgba(255,255,255,.95)', color: '#4a3fd6', minHeight: 56, fontSize: 17, padding: '0 32px' }}
          >
            Crear cuenta gratis <ArrowRight size={18} />
          </Link>
        </div>
      </section>

      <Footer />
    </div>
  );
}
