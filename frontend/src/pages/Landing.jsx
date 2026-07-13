import { Link } from 'react-router-dom';
import {
  Wallet, Bitcoin, ShieldCheck, Clock, Smartphone, LayoutDashboard,
  ArrowRight, CheckCircle2, TrendingUp,
} from 'lucide-react';
import { useRate } from '../contexts/RateContext';
import { fmt } from '../utils/format';
import Footer from '../components/Footer';

/**
 * Landing.jsx — Pagina publica de risappbr.com para visitantes SIN sesion.
 *
 * IMPORTANTE (regla de negocio explicita): esta pagina NO debe mencionar remesas,
 * transferencias internacionales, "paga en moneda local y recibe en dolares/VES",
 * ni mostrar un cotizador que calcule cuanto recibe alguien en otra moneda. Todo eso
 * se reformula como "Operaciones Digitales" de forma generica. Los indicadores
 * economicos (tasas de mercado) SI se pueden mostrar, pero como informacion general,
 * no como "tu tasa de envio". El detalle real de cada operacion vive DESPUES del
 * login (Dashboard, Recharge, Send, etc.) — esta pagina es solo la puerta de entrada.
 *
 * Usuarios autenticados nunca ven esta pagina: App.jsx la muestra solo cuando no
 * hay sesion activa en la ruta "/".
 */

const FEATURES = [
  {
    icon: Wallet,
    color: '#5B4FE9',
    title: 'Recargas digitales',
    desc: 'Recarga tu cuenta con distintos métodos de pago, de forma rápida y segura.',
  },
  {
    icon: Bitcoin,
    color: '#f59e0b',
    title: 'Operaciones con Bitcoin',
    desc: 'Opera con Bitcoin por la red Lightning, con confirmación casi inmediata.',
  },
  {
    icon: TrendingUp,
    color: '#2775CA',
    title: 'Créditos digitales USDTRIS / USDCRIS',
    desc: 'Activa créditos digitales respaldados en USDT o USDC dentro de tu cuenta.',
  },
  {
    icon: LayoutDashboard,
    color: '#16a34a',
    title: 'Panel de control personal',
    desc: 'Consulta tu historial y controla todas tus operaciones desde un solo lugar.',
  },
];

const TRUST_ITEMS = [
  { icon: Clock, title: 'Acreditación al instante', desc: 'Tus operaciones se reflejan en tu cuenta apenas se confirman, sin esperas.' },
  { icon: ShieldCheck, title: 'Operaciones verificadas', desc: 'Cada operación se valida con verificación de seguridad antes de acreditarse.' },
  { icon: Smartphone, title: '100% desde el navegador', desc: 'Sin instalar nada: gestiona tu cuenta desde risappbr.com.' },
];

function MarketIndicators() {
  const { rates, loading } = useRate();
  const items = [
    { label: 'USD', value: rates?.bcv_usd_ves },
    { label: 'EUR', value: rates?.bcv_eur_ves },
  ].filter((i) => i.value);

  if (loading || items.length === 0) return null;

  return (
    <div style={{
      display: 'flex', gap: 16, flexWrap: 'wrap', justifyContent: 'center',
      backgroundColor: '#fff', borderRadius: 16, padding: '16px 24px', border: '1px solid #eef0f4',
      boxShadow: '0 8px 20px rgba(91,79,233,0.08)', maxWidth: 420, width: '100%',
    }}>
      {items.map((i) => (
        <div key={i.label} style={{ textAlign: 'center', minWidth: 110 }}>
          <p style={{ margin: '0 0 4px 0', fontSize: 11, fontWeight: 700, color: '#9ca3af', letterSpacing: '0.04em' }}>
            {i.label} / VES
          </p>
          <p style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#3B3A9E' }}>
            {fmt(i.value)}
          </p>
        </div>
      ))}
      <p style={{ width: '100%', margin: '10px 0 0 0', fontSize: 11, color: '#9ca3af', textAlign: 'center' }}>
        Indicador de mercado, solo referencial.
      </p>
    </div>
  );
}

export default function Landing() {
  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#ffffff', fontFamily: 'Inter, Helvetica, -apple-system, sans-serif' }}>
      {/* Header */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 20, backgroundColor: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(8px)',
        borderBottom: '1px solid #f0f0f5', padding: '14px 20px',
      }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <img src="/logo-ris.jpeg" alt="RIS App" style={{ height: 36, borderRadius: 8 }} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Link to="/login" style={{
              padding: '10px 18px', borderRadius: 10, fontSize: 14, fontWeight: 600, color: '#374151',
              textDecoration: 'none',
            }}>
              Iniciar sesión
            </Link>
            <Link to="/register" style={{
              padding: '10px 20px', borderRadius: 10, fontSize: 14, fontWeight: 700, color: '#fff',
              background: 'linear-gradient(135deg, #5B4FE9 0%, #3B3A9E 100%)', textDecoration: 'none',
            }}>
              Crear cuenta
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section style={{ padding: '64px 20px 48px', background: 'radial-gradient(ellipse at top left, #f0eeff 0%, #ffffff 55%)' }}>
        <div style={{
          maxWidth: 1100, margin: '0 auto', display: 'flex', gap: 48, alignItems: 'center',
          flexWrap: 'wrap',
        }}>
          <div style={{ flex: '1 1 420px', minWidth: 300 }}>
            <h1 style={{ fontSize: 42, fontWeight: 800, color: '#111827', lineHeight: 1.15, margin: '0 0 16px 0' }}>
              Tu plataforma de <span style={{ color: '#5B4FE9' }}>operaciones digitales</span>
            </h1>
            <p style={{ fontSize: 17, color: '#6b7280', lineHeight: 1.6, margin: '0 0 28px 0' }}>
              Recarga tu cuenta, opera con Bitcoin y activa créditos digitales respaldados
              en USDT o USDC. Todo desde una sola cuenta, sin salir de la app.
            </p>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <Link to="/register" style={{
                display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 26px', borderRadius: 14,
                fontSize: 15, fontWeight: 700, color: '#fff', textDecoration: 'none',
                background: 'linear-gradient(135deg, #5B4FE9 0%, #3B3A9E 100%)',
                boxShadow: '0 10px 24px rgba(91,79,233,0.28)',
              }}>
                Crear cuenta gratis <ArrowRight size={17} />
              </Link>
              <Link to="/login" style={{
                display: 'inline-flex', alignItems: 'center', padding: '15px 26px', borderRadius: 14,
                fontSize: 15, fontWeight: 700, color: '#374151', textDecoration: 'none',
                border: '1.5px solid #e5e7eb',
              }}>
                Ya tengo cuenta
              </Link>
            </div>
          </div>

          <div style={{ flex: '1 1 380px', display: 'flex', justifyContent: 'center' }}>
            <MarketIndicators />
          </div>
        </div>
      </section>

      {/* Trust row */}
      <section style={{ padding: '8px 20px 56px' }}>
        <div style={{
          maxWidth: 1100, margin: '0 auto', display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 20,
        }}>
          {TRUST_ITEMS.map((t) => (
            <div key={t.title} style={{ display: 'flex', gap: 14, padding: 20, borderRadius: 16, backgroundColor: '#f9fafb' }}>
              <div style={{
                width: 44, height: 44, borderRadius: 12, backgroundColor: '#eef0ff', display: 'flex',
                alignItems: 'center', justifyContent: 'center', flexShrink: 0,
              }}>
                <t.icon size={22} color="#5B4FE9" />
              </div>
              <div>
                <p style={{ margin: '0 0 4px 0', fontWeight: 700, fontSize: 15, color: '#111827' }}>{t.title}</p>
                <p style={{ margin: 0, fontSize: 13, color: '#6b7280', lineHeight: 1.5 }}>{t.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Features grid */}
      <section style={{ padding: '32px 20px 64px', backgroundColor: '#f9fafb' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <h2 style={{ fontSize: 28, fontWeight: 800, color: '#111827', textAlign: 'center', margin: '0 0 8px 0' }}>
            Todo lo que puedes hacer con RIS App
          </h2>
          <p style={{ fontSize: 15, color: '#6b7280', textAlign: 'center', margin: '0 0 40px 0' }}>
            Una sola cuenta para tus operaciones digitales.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20 }}>
            {FEATURES.map((f) => (
              <Link key={f.title} to="/register" style={{
                display: 'block', padding: 24, borderRadius: 18, backgroundColor: '#fff',
                border: '1px solid #eef0f4', textDecoration: 'none', boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
              }}>
                <div style={{
                  width: 46, height: 46, borderRadius: 12, backgroundColor: `${f.color}18`, display: 'flex',
                  alignItems: 'center', justifyContent: 'center', marginBottom: 14,
                }}>
                  <f.icon size={22} color={f.color} />
                </div>
                <p style={{ margin: '0 0 6px 0', fontWeight: 700, fontSize: 16, color: '#111827' }}>{f.title}</p>
                <p style={{ margin: 0, fontSize: 13.5, color: '#6b7280', lineHeight: 1.5 }}>{f.desc}</p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Security */}
      <section style={{ padding: '56px 20px' }}>
        <div style={{
          maxWidth: 1100, margin: '0 auto', display: 'flex', gap: 40, alignItems: 'center', flexWrap: 'wrap',
        }}>
          <div style={{ flex: '1 1 320px' }}>
            <div style={{
              width: 56, height: 56, borderRadius: 16, background: 'linear-gradient(135deg, #5B4FE9 0%, #3B3A9E 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16,
            }}>
              <ShieldCheck size={26} color="#fff" />
            </div>
            <h3 style={{ fontSize: 24, fontWeight: 800, color: '#111827', margin: '0 0 12px 0' }}>
              Tu cuenta y tus datos, protegidos
            </h3>
            <p style={{ fontSize: 15, color: '#6b7280', lineHeight: 1.6, margin: 0 }}>
              Cada operación se procesa con verificación de seguridad antes de acreditarse,
              y mantenemos una separación estricta entre tus distintos saldos.
            </p>
          </div>
          <div style={{ flex: '1 1 320px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[
              'Acreditación atómica: nunca se duplica ni se pierde una operación confirmada.',
              'Separación estricta entre tus distintos saldos y créditos digitales.',
              'Verificación de identidad antes de operar montos mayores.',
            ].map((line) => (
              <div key={line} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <CheckCircle2 size={18} color="#16a34a" style={{ flexShrink: 0, marginTop: 2 }} />
                <p style={{ margin: 0, fontSize: 14, color: '#374151' }}>{line}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section style={{ padding: '24px 20px 64px' }}>
        <div style={{
          maxWidth: 1100, margin: '0 auto', borderRadius: 24, padding: '48px 32px', textAlign: 'center',
          background: 'linear-gradient(135deg, #5B4FE9 0%, #3B3A9E 100%)',
        }}>
          <h2 style={{ fontSize: 26, fontWeight: 800, color: '#fff', margin: '0 0 10px 0' }}>
            Crea tu cuenta y empieza a operar
          </h2>
          <p style={{ fontSize: 15, color: 'rgba(255,255,255,0.85)', margin: '0 0 24px 0' }}>
            Sin papeleos complicados.
          </p>
          <Link to="/register" style={{
            display: 'inline-flex', alignItems: 'center', gap: 8, padding: '15px 28px', borderRadius: 14,
            fontSize: 15, fontWeight: 700, color: '#5B4FE9', backgroundColor: '#fff', textDecoration: 'none',
          }}>
            Crear cuenta gratis <ArrowRight size={17} />
          </Link>
        </div>
      </section>

      <Footer />
    </div>
  );
}
