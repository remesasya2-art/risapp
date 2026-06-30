import { Link } from 'react-router-dom';

export default function Footer() {
  const linkStyle = { color: '#6b7280', textDecoration: 'none', fontSize: '13px' };
  const colTitle = { color: '#374151', fontSize: '13px', fontWeight: 700, marginBottom: '10px' };

  return (
    <footer style={{ backgroundColor: '#f9fafb', borderTop: '1px solid #e5e7eb', padding: '32px 20px', marginTop: '40px' }}>
      <div style={{ maxWidth: '1100px', margin: '0 auto', display: 'flex', flexWrap: 'wrap', gap: '32px', justifyContent: 'space-between' }}>
        <div style={{ maxWidth: '320px' }}>
          <p style={{ fontWeight: 800, fontSize: '16px', color: '#1f2937', margin: '0 0 6px 0' }}>RIS App</p>
          <p style={{ fontSize: '12px', color: '#6b7280', margin: '0 0 4px 0' }}>SAIPHA SERVICIOS DIGITAIS</p>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0 0 4px 0' }}>J. DEL CARMEN HERNANDEZ BARRETO</p>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: '0 0 4px 0' }}>CNPJ: 68.994.057/0001-61</p>
          <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0 }}>Rua Monte Roraima, S/N, Vila Nova, Pacaraima – RR, CEP 69355-000, Brasil</p>
        </div>
        <div>
          <p style={colTitle}>Legal</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <Link to="/legal#privacidad" style={linkStyle}>Política de Privacidad</Link>
            <Link to="/legal#terminos" style={linkStyle}>Términos y Condiciones</Link>
            <Link to="/legal#reembolsos" style={linkStyle}>Reembolsos y Devoluciones</Link>
            <Link to="/legal#cancelacion" style={linkStyle}>Cancelación de Cuenta</Link>
            <Link to="/legal#datos-fiscales" style={linkStyle}>Información Fiscal</Link>
          </div>
        </div>
        <div>
          <p style={colTitle}>Contacto</p>
          <a href="mailto:saipha.servicios.digitais@gmail.com" style={linkStyle}>saipha.servicios.digitais@gmail.com</a>
        </div>
      </div>
      <div style={{ maxWidth: '1100px', margin: '24px auto 0', borderTop: '1px solid #e5e7eb', paddingTop: '16px' }}>
        <p style={{ fontSize: '12px', color: '#9ca3af', margin: 0, textAlign: 'center' }}>
          © {new Date().getFullYear()} SAIPHA SERVICIOS DIGITAIS · CNPJ 68.994.057/0001-61 · Todos los derechos reservados.
        </p>
      </div>
    </footer>
  );
}
