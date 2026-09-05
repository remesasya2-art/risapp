import { Link } from 'react-router-dom';

export default function Footer() {
  const linkStyle = { color: '#6b7280', textDecoration: 'none', fontSize: '13px' };
  const colTitle = { color: '#374151', fontSize: '13px', fontWeight: 700, marginBottom: '10px' };

  return (
    <footer style={{ backgroundColor: '#f9fafb', borderTop: '1px solid #e5e7eb', padding: '32px 20px', marginTop: '40px' }}>
      <div style={{ maxWidth: '1100px', margin: '0 auto', display: 'flex', flexWrap: 'wrap', gap: '32px', justifyContent: 'space-between' }}>
        <div style={{ maxWidth: '320px' }}>
          <p style={{ fontWeight: 800, fontSize: '16px', color: '#1f2937', margin: '0 0 6px 0' }}>RIS App</p>
          <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>Administrado por SAIPHA SERVICIOS DIGITAIS</p>
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
      <div style={{ maxWidth: '1100px', margin: '24px auto 0', borderTop: '1px solid #e5e7eb', paddingTop: '16px' }}>
        <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0, textAlign: 'center' }}>
          © {new Date().getFullYear()} RIS App · Todos los derechos reservados.
        </p>
      </div>
    </footer>
  );
}
