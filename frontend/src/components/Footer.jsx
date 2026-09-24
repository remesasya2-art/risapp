import { Link } from 'react-router-dom';

// Los colores son los nombres de index.css y no valores: el pie aparece en la
// portada y en el login, que ya cambian entre claro y oscuro. Fuera de una
// pantalla con `.con-tema` los nombres valen lo del modo claro, así que en
// una pantalla que todavía no pasó el pie se sigue viendo como antes.
export default function Footer() {
  const linkStyle = { color: 'var(--t-texto-2)', textDecoration: 'none', fontSize: '13px' };
  const colTitle = { color: 'var(--t-texto)', fontSize: '13px', fontWeight: 700, margin: '0 0 12px 0' };

  return (
    <footer style={{ position: 'relative', zIndex: 1, borderTop: '1px solid var(--t-linea)', padding: '40px 20px 32px', marginTop: '40px' }}>
      <div style={{ maxWidth: '1120px', margin: '0 auto', display: 'flex', flexWrap: 'wrap', gap: '32px', justifyContent: 'space-between' }}>
        <div style={{ maxWidth: '320px' }}>
          <p style={{ display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 700, fontSize: '15px', color: 'var(--t-texto)', margin: '0 0 8px 0' }}>
            <img src="/logo-ris.png" alt="" width={28} height={28} className="t-logo" style={{ borderRadius: '7px' }} />
            RISApp
          </p>
          <p style={{ fontSize: '12px', color: 'var(--t-texto-2)', margin: '0 0 4px 0' }}>Administrado por SAIPHA SERVICIOS DIGITAIS</p>
        </div>
        <div>
          <p style={colTitle}>Legal</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <Link to="/legal#privacidad" style={linkStyle}>Política de privacidad</Link>
            <Link to="/legal#terminos" style={linkStyle}>Términos y condiciones</Link>
            <Link to="/legal#reembolsos" style={linkStyle}>Reembolsos y devoluciones</Link>
            <Link to="/legal#cancelacion" style={linkStyle}>Cancelación de cuenta</Link>
            <Link to="/legal#empresa" style={linkStyle}>Información de la empresa</Link>
          </div>
        </div>
        <div>
          <p style={colTitle}>Contacto</p>
          <Link to="/support" style={linkStyle}>Centro de ayuda</Link>
        </div>
      </div>
      <div style={{ maxWidth: '1120px', margin: '24px auto 0', borderTop: '1px solid var(--t-linea)', paddingTop: '16px' }}>
        <p style={{ fontSize: '12px', color: 'var(--t-texto-3)', margin: 0, textAlign: 'center' }}>
          © {new Date().getFullYear()} RISApp · Todos los derechos reservados.
        </p>
      </div>
    </footer>
  );
}
