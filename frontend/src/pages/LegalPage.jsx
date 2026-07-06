import { useEffect } from 'react';

// Página única con las 5 políticas. El Footer enlaza a /legal#privacidad, etc.
export default function LegalPage() {
  // Al cargar, si hay un #ancla en la URL, desplaza hasta esa sección
  useEffect(() => {
    const id = window.location.hash.replace('#', '');
    if (id) {
      const el = document.getElementById(id);
      if (el) setTimeout(() => el.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    }
  }, []);

  const wrap = { maxWidth: '820px', margin: '0 auto', padding: '40px 20px 80px', color: '#1f2937', lineHeight: 1.7 };
  const h1 = { fontSize: '26px', fontWeight: 800, margin: '40px 0 8px', color: '#111827', scrollMarginTop: '80px' };
  const h2 = { fontSize: '18px', fontWeight: 700, margin: '22px 0 6px', color: '#374151' };
  const p = { fontSize: '15px', color: '#374151', margin: '0 0 12px' };
  const li = { fontSize: '15px', color: '#374151', margin: '0 0 6px' };
  const muted = { fontSize: '13px', color: '#9ca3af' };

  return (
    <div style={{ backgroundColor: '#fff', minHeight: '100vh' }}>
      <div style={wrap}>
        <h1 style={{ fontSize: '32px', fontWeight: 800, marginBottom: '4px' }}>Políticas y Términos Legales</h1>
        <p style={muted}>RIS App · SAIPHA SERVICIOS DIGITAIS · Última actualización: 29 de junio de 2026</p>

        {/* 1. PRIVACIDAD */}
        <h1 id="privacidad" style={h1}>1. Política de Privacidad</h1>
        <p style={p}>En SAIPHA SERVICIOS DIGITAIS (J. DEL CARMEN HERNANDEZ BARRETO, CNPJ 66.994.057/0001-61), operadora de la plataforma RIS App (risappbr.com), valoramos y protegemos la privacidad de nuestros usuarios. Esta Política explica qué datos recopilamos, con qué finalidad y cómo los protegemos, en conformidad con la Lei Geral de Proteção de Dados (LGPD – Lei nº 13.709/2018) de Brasil.</p>
        <h2 style={h2}>1.1. Datos que recopilamos</h2>
        <ul>
          <li style={li}>Datos de identificación: nombre completo, documento de identidad y fecha de nacimiento.</li>
          <li style={li}>Datos de contacto: correo electrónico y número de teléfono.</li>
          <li style={li}>Datos de la cuenta: nombre de usuario, historial de operaciones y saldo dentro de la plataforma.</li>
          <li style={li}>Datos de verificación de identidad (KYC): documentos e imágenes que el usuario aporta voluntariamente.</li>
          <li style={li}>Datos técnicos: dirección IP, tipo de dispositivo y datos de uso de la aplicación.</li>
        </ul>
        <h2 style={h2}>1.2. Finalidad del tratamiento</h2>
        <ul>
          <li style={li}>Crear y administrar la cuenta del usuario.</li>
          <li style={li}>Procesar las recargas de saldo y el consumo de servicios digitales dentro de la plataforma.</li>
          <li style={li}>Verificar la identidad del usuario y prevenir fraudes.</li>
          <li style={li}>Cumplir obligaciones legales, fiscales y regulatorias.</li>
          <li style={li}>Brindar atención al cliente y mejorar el servicio.</li>
        </ul>
        <h2 style={h2}>1.3. Compartición de datos</h2>
        <p style={p}>No vendemos datos personales. Podemos compartirlos únicamente con proveedores de procesamiento de pagos externos, proveedores tecnológicos que nos prestan servicios (alojamiento, envío de correos) y autoridades competentes cuando la ley lo exija.</p>
        <h2 style={h2}>1.4. Derechos del titular</h2>
        <p style={p}>Conforme a la LGPD, el usuario puede solicitar el acceso, la corrección, la portabilidad o la eliminación de sus datos escribiendo a saipha.servicios.digitais@gmail.com.</p>
        <h2 style={h2}>1.5. Conservación y seguridad</h2>
        <p style={p}>Conservamos los datos durante el tiempo necesario para prestar el servicio y cumplir obligaciones legales y fiscales. Aplicamos medidas técnicas y organizativas razonables para proteger la información.</p>

        {/* 2. TÉRMINOS */}
        <h1 id="terminos" style={h1}>2. Términos y Condiciones de Uso</h1>
        <p style={p}>Estos Términos regulan el uso de la plataforma RIS App (risappbr.com), operada por J. DEL CARMEN HERNANDEZ BARRETO (SAIPHA SERVICIOS DIGITAIS), CNPJ 66.994.057/0001-61. Al registrarse y utilizar la plataforma, el usuario acepta estos Términos.</p>
        <h2 style={h2}>2.1. Descripción del servicio</h2>
        <p style={p}>La plataforma permite registrar una cuenta y realizar recargas de saldo. Dicho saldo se utiliza exclusivamente para el consumo de los servicios digitales disponibles dentro de la propia plataforma. El saldo y los servicios son de uso interno de la aplicación.</p>
        <h2 style={h2}>2.2. Registro y cuenta</h2>
        <ul>
          <li style={li}>El usuario debe ser mayor de edad y proporcionar información veraz y actualizada.</li>
          <li style={li}>El usuario es responsable de la confidencialidad de sus credenciales de acceso.</li>
          <li style={li}>Podemos solicitar verificación de identidad (KYC) para habilitar ciertas funciones.</li>
        </ul>
        <h2 style={h2}>2.3. Recargas y uso del saldo</h2>
        <ul>
          <li style={li}>Las recargas se realizan a través de proveedores de pago externos.</li>
          <li style={li}>El saldo acreditado se destina al consumo de servicios digitales dentro de la plataforma.</li>
          <li style={li}>Los importes, comisiones o tasas aplicables se informan antes de confirmar cada operación.</li>
        </ul>
        <h2 style={h2}>2.4. Obligaciones del usuario</h2>
        <p style={p}>El usuario se compromete a no utilizar la plataforma para fines ilícitos, fraudulentos o no autorizados. El incumplimiento puede derivar en la suspensión o cancelación de la cuenta.</p>
        <h2 style={h2}>2.5. Limitación de responsabilidad</h2>
        <p style={p}>La plataforma se ofrece &ldquo;tal cual&rdquo;. En la medida permitida por la ley, no respondemos por daños indirectos derivados de interrupciones del servicio, errores del usuario o causas de fuerza mayor.</p>
        <h2 style={h2}>2.6. Ley aplicable</h2>
        <p style={p}>Estos Términos se rigen por las leyes de la República Federativa de Brasil. Cualquier controversia se someterá a los tribunales competentes del domicilio de la empresa.</p>

        {/* 3. REEMBOLSOS */}
        <h1 id="reembolsos" style={h1}>3. Política de Reembolsos y Devoluciones</h1>
        <h2 style={h2}>3.1. Principio general</h2>
        <p style={p}>Las recargas de saldo se acreditan para el consumo de servicios digitales dentro de la plataforma. Una vez que el saldo ha sido consumido en un servicio, la operación se considera prestada y, por su naturaleza digital, no es reembolsable, salvo en los casos previstos a continuación.</p>
        <h2 style={h2}>3.2. Casos en que procede el reembolso</h2>
        <ul>
          <li style={li}>Cobro duplicado o erróneo.</li>
          <li style={li}>Recarga no acreditada en la cuenta del usuario.</li>
          <li style={li}>Operación no reconocida por el usuario, sujeta a verificación.</li>
        </ul>
        <h2 style={h2}>3.3. Casos en que NO procede el reembolso</h2>
        <ul>
          <li style={li}>Saldo ya consumido en un servicio digital prestado dentro de la plataforma.</li>
          <li style={li}>Solicitudes derivadas de un uso incorrecto por parte del usuario.</li>
          <li style={li}>Cuentas suspendidas o canceladas por incumplimiento de los Términos.</li>
        </ul>
        <h2 style={h2}>3.4. Cómo solicitar un reembolso</h2>
        <p style={p}>Escriba a saipha.servicios.digitais@gmail.com indicando su nombre, el comprobante de la operación y el motivo, preferentemente dentro de los 7 días posteriores a la operación.</p>
        <h2 style={h2}>3.5. Plazos</h2>
        <p style={p}>Una vez aprobada la solicitud, el reembolso se procesa a través del mismo proveedor de pago utilizado. El tiempo de acreditación depende de dicho proveedor y de la entidad financiera del usuario, y puede demorar varios días hábiles.</p>

        {/* 4. CANCELACIÓN */}
        <h1 id="cancelacion" style={h1}>4. Política de Cancelación de Cuenta</h1>
        <p style={p}>El usuario puede solicitar la cancelación de su cuenta en cualquier momento.</p>
        <h2 style={h2}>4.1. Cómo cancelar</h2>
        <p style={p}>Escriba a saipha.servicios.digitais@gmail.com desde el correo registrado solicitando la baja. Verificaremos la identidad antes de proceder.</p>
        <h2 style={h2}>4.2. Saldo pendiente</h2>
        <p style={p}>Antes de cancelar, el usuario debe considerar el saldo disponible. Indicaremos el procedimiento aplicable para el saldo no consumido, conforme a la Política de Reembolsos.</p>
        <h2 style={h2}>4.3. Conservación de información</h2>
        <p style={p}>Tras la cancelación, podemos conservar cierta información durante el plazo que exijan las obligaciones legales, fiscales y de prevención de fraude.</p>
        <h2 style={h2}>4.4. Cancelación por parte de la plataforma</h2>
        <p style={p}>Podemos suspender o cancelar una cuenta que incumpla estos Términos, que presente actividad fraudulenta o que la ley nos obligue a cerrar.</p>

        {/* 5. DATOS FISCALES */}
        <h1 id="datos-fiscales" style={h1}>5. Información Fiscal y de la Empresa</h1>
        <p style={p}>La plataforma RIS App es operada por:</p>
        <ul>
          <li style={li}>Razón social: J. DEL CARMEN HERNANDEZ BARRETO</li>
          <li style={li}>Nombre fantasía: SAIPHA SERVICIOS DIGITAIS</li>
          <li style={li}>CNPJ: 66.994.057/0001-61</li>
          <li style={li}>Dirección: Rua Monte Roraima, S/N, Bairro Vila Nova, Pacaraima – RR, CEP 69345-000, Brasil</li>
          <li style={li}>Correo de contacto: saipha.servicios.digitais@gmail.com</li>
          <li style={li}>Sitio web: risappbr.com</li>
        </ul>
        <p style={muted}>Para consultas administrativas, fiscales o de facturación, contacte a saipha.servicios.digitais@gmail.com.</p>
      </div>
    </div>
  );
}
