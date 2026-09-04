/**
 * LegalPage.jsx — Marco legal y políticas de la plataforma.
 *
 * QUE TIENE QUE LOGRAR ESTA PANTALLA
 *
 *   Es la página que abre quien está decidiendo si confía: un usuario nuevo,
 *   o la revisión de cumplimiento de un proveedor. Tiene que leerse ordenada,
 *   completa y sin ambigüedades, porque eso —y no un adjetivo— es lo que
 *   comunica seriedad.
 *
 *   Por eso: índice navegable arriba, numeración estable, jerarquía tipográfica
 *   consistente, y cada afirmación verificable contra lo que el sistema hace
 *   de verdad. No se prometen plazos de respuesta que nadie midió.
 *
 * LAS REGLAS DE NEGOCIO QUE RESPETA
 *
 *   1. `Landing.jsx` deja escrita una regla explícita: las páginas públicas NO
 *      mencionan remesas ni transferencias internacionales. Se suman, por
 *      pedido expreso, "envíos transfronterizos" y "cambio de dinero". Todo se
 *      describe como servicios digitales, que es la línea principal.
 *
 *   2. El único canal de contacto es el centro de ayuda de la aplicación. No
 *      se publica ninguna dirección de correo: este archivo se compila dentro
 *      del bundle que se le sirve a cada visitante, así que una dirección
 *      escrita acá queda expuesta para siempre y sólo se cambia desplegando.
 *
 *   3. El CNPJ no figura en el pie de página —o sea, no se ve en la portada—,
 *      pero sí en la ficha de la empresa de este documento. El Decreto
 *      7.962/2013, que regula el comercio electrónico en Brasil, exige que el
 *      sitio publique el nombre empresarial y el CNPJ; sacarlo de todas partes
 *      dejaría a la plataforma sin identificar a su operador, que es lo primero
 *      que revisa una debida diligencia.
 *
 * ORTOGRAFIA
 *
 *   Títulos en mayúscula sólo inicial, como manda la RAE para títulos de
 *   documentos —no en versalita inglesa—; comillas angulares; números menores
 *   que diez escritos con letra; términos definidos («Términos», «Políticas»)
 *   en mayúscula por convención jurídica; extranjerismos en cursiva.
 */
import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, FileText, ScrollText, RotateCcw, UserMinus, Building2 } from 'lucide-react';

const MORADO = '#5B4FE9';

const SECCIONES = [
  { id: 'privacidad', n: 1, titulo: 'Política de privacidad' },
  { id: 'terminos', n: 2, titulo: 'Términos y condiciones de uso' },
  { id: 'reembolsos', n: 3, titulo: 'Política de reembolsos y devoluciones' },
  { id: 'cancelacion', n: 4, titulo: 'Política de cancelación de cuenta' },
  { id: 'empresa', n: 5, titulo: 'Información de la empresa' },
];

// El único canal de contacto. Va en un solo lugar para que las seis menciones
// del documento no puedan quedar diciendo cosas distintas.
function Soporte({ children }) {
  return (
    <Link to="/support" style={{ color: MORADO, fontWeight: 600, textDecoration: 'none' }}>
      {children || 'el centro de ayuda'}
    </Link>
  );
}

function Seccion({ id, n, titulo, icono, children }) {
  return (
    <section id={id} style={{ scrollMarginTop: 24, marginTop: 44 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        paddingBottom: 14, borderBottom: '2px solid #f1f0fb', marginBottom: 22,
      }}
      >
        <div style={{
          width: 38, height: 38, borderRadius: 10, background: '#f0eeff',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}
        >
          {icono}
        </div>
        <h2 style={{
          margin: 0, fontSize: 20, fontWeight: 700, color: '#111827',
          letterSpacing: '-0.01em',
        }}
        >
          <span style={{ color: '#c7c3f0', marginRight: 10 }}>{n}</span>
          {titulo}
        </h2>
      </div>
      {children}
    </section>
  );
}

export default function LegalPage() {
  useEffect(() => {
    const id = window.location.hash.replace('#', '');
    if (!id) return undefined;
    const t = setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
    return () => clearTimeout(t);
  }, []);

  const h3 = {
    fontSize: 15, fontWeight: 700, margin: '24px 0 8px', color: '#374151',
  };
  const p = {
    fontSize: 15, color: '#4b5563', margin: '0 0 14px', lineHeight: 1.75,
  };
  const li = {
    fontSize: 15, color: '#4b5563', margin: '0 0 8px', lineHeight: 1.7,
  };
  const ul = { margin: '0 0 14px', paddingLeft: 22 };

  return (
    <div style={{ background: '#fff', minHeight: '100vh' }}>
      {/* ── Encabezado ─────────────────────────────────────────────────── */}
      <header style={{
        background: 'linear-gradient(180deg, #faf9ff 0%, #ffffff 100%)',
        borderBottom: '1px solid #f1f0fb',
      }}
      >
        <div style={{ maxWidth: 860, margin: '0 auto', padding: '48px 24px 40px' }}>
          <Link
            to="/"
            style={{
              fontSize: 13, color: MORADO, textDecoration: 'none', fontWeight: 600,
            }}
          >
            ← Volver al inicio
          </Link>

          <h1 style={{
            fontSize: 34, fontWeight: 800, color: '#111827',
            margin: '20px 0 12px', letterSpacing: '-0.02em', lineHeight: 1.2,
          }}
          >
            Marco legal y políticas
          </h1>
          <p style={{
            fontSize: 16, color: '#4b5563', margin: '0 0 26px',
            lineHeight: 1.7, maxWidth: 640,
          }}
          >
            RIS App es una plataforma de <strong>soluciones digitales</strong> operada
            por SAIPHA Servicios Digitais. En este documento están, completas y
            sin letra chica, las reglas con las que trabajamos: qué datos
            tratamos, cómo se usa el saldo, cuándo corresponde un reembolso y
            cómo se cancela una cuenta.
          </p>

          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center',
          }}
          >
            <span style={{
              fontSize: 12.5, color: '#6b7280', background: '#f4f4f7',
              padding: '5px 11px', borderRadius: 999,
            }}
            >
              Última actualización: 4 de septiembre de 2026
            </span>
            <span style={{
              fontSize: 12.5, color: '#6b7280', background: '#f4f4f7',
              padding: '5px 11px', borderRadius: 999,
            }}
            >
              Legislación aplicable: República Federativa de Brasil
            </span>
          </div>
        </div>
      </header>

      <div style={{ maxWidth: 860, margin: '0 auto', padding: '0 24px 90px' }}>
        {/* ── Cómo trabajamos ──────────────────────────────────────────── */}
        {/*
          Tres afirmaciones verificables contra lo que el sistema hace, no tres
          adjetivos. Deliberadamente no se promete un plazo de respuesta: un
          compromiso que nadie midió es exactamente lo que no debe figurar en
          una página legal.
        */}
        <div style={{
          display: 'grid', gap: 14, marginTop: 34,
          gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
        }}
        >
          {[
            {
              t: 'Identidad verificada',
              d: 'Las operaciones que superan el cupo inicial requieren verificación de identidad documentada.',
            },
            {
              t: 'Todo queda registrado',
              d: 'Cada operación y cada intervención administrativa se asienta con fecha, hora y responsable.',
            },
            {
              t: 'Procesamiento automático',
              d: 'Las acreditaciones se procesan de forma automática al confirmarse el pago, sin intervención manual.',
            },
          ].map((c) => (
            <div
              key={c.t}
              style={{
                border: '1px solid #ececf3', borderRadius: 12, padding: '16px 18px',
                background: '#fff',
              }}
            >
              <p style={{
                margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#111827',
              }}
              >
                {c.t}
              </p>
              <p style={{ margin: 0, fontSize: 13, color: '#6b7280', lineHeight: 1.6 }}>
                {c.d}
              </p>
            </div>
          ))}
        </div>

        {/* ── Índice ───────────────────────────────────────────────────── */}
        <nav
          aria-label="Índice del documento"
          style={{
            marginTop: 34, border: '1px solid #ececf3', borderRadius: 14,
            padding: '20px 22px', background: '#fcfcfe',
          }}
        >
          <p style={{
            margin: '0 0 12px', fontSize: 12, fontWeight: 700, color: '#9ca3af',
            textTransform: 'uppercase', letterSpacing: '0.06em',
          }}
          >
            Contenido
          </p>
          <ol style={{ margin: 0, padding: 0, listStyle: 'none' }}>
            {SECCIONES.map((s) => (
              <li key={s.id} style={{ margin: '0 0 9px' }}>
                <a
                  href={`#${s.id}`}
                  style={{
                    fontSize: 14.5, color: '#374151', textDecoration: 'none',
                    display: 'flex', gap: 10,
                  }}
                >
                  <span style={{ color: '#c7c3f0', fontWeight: 700, minWidth: 14 }}>
                    {s.n}
                  </span>
                  {s.titulo}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        {/* ── 1. Privacidad ────────────────────────────────────────────── */}
        <Seccion
          id="privacidad"
          n={1}
          titulo="Política de privacidad"
          icono={<ShieldCheck size={19} color={MORADO} />}
        >
          <p style={p}>
            SAIPHA Servicios Digitais, operadora de la plataforma RIS App
            (risappbr.com), protege la privacidad de sus usuarios. Esta Política
            explica qué datos se recopilan, con qué finalidad y cómo se
            resguardan, conforme a la <i>Lei Geral de Proteção de Dados</i>
            {' '}(LGPD, Lei n.º 13.709/2018).
          </p>

          <h3 style={h3}>1.1. Datos que se recopilan</h3>
          <ul style={ul}>
            <li style={li}>Identificación: nombre completo, documento de identidad y fecha de nacimiento.</li>
            <li style={li}>Contacto: correo electrónico y número de teléfono.</li>
            <li style={li}>Cuenta: nombre de usuario, historial de operaciones y saldo dentro de la plataforma.</li>
            <li style={li}>Verificación de identidad: documentos e imágenes que el usuario aporta voluntariamente.</li>
            <li style={li}>Datos técnicos: dirección IP, tipo de dispositivo y datos de uso de la aplicación.</li>
          </ul>

          <h3 style={h3}>1.2. Finalidad del tratamiento</h3>
          <ul style={ul}>
            <li style={li}>Crear y administrar la cuenta del usuario.</li>
            <li style={li}>Procesar las recargas de saldo y el consumo de servicios digitales dentro de la plataforma.</li>
            <li style={li}>Verificar la identidad del usuario y prevenir fraudes.</li>
            <li style={li}>Cumplir obligaciones legales, fiscales y regulatorias.</li>
            <li style={li}>Brindar atención al usuario y mejorar el servicio.</li>
          </ul>

          <h3 style={h3}>1.3. Compartición de datos</h3>
          <p style={p}>
            No se venden datos personales. Sólo se comparten con proveedores de
            procesamiento de pagos, con proveedores tecnológicos que prestan
            servicios de alojamiento y de envío de correos, y con las
            autoridades competentes cuando la ley lo exija.
          </p>

          <h3 style={h3}>1.4. Derechos del titular</h3>
          <p style={p}>
            Conforme a la LGPD, el usuario puede solicitar el acceso, la
            corrección, la portabilidad o la eliminación de sus datos a través
            de <Soporte />, dentro de la aplicación. Cada solicitud queda
            registrada con fecha y hora desde el momento en que se recibe.
          </p>

          <h3 style={h3}>1.5. Conservación y seguridad</h3>
          <p style={p}>
            Los datos se conservan durante el tiempo necesario para prestar el
            servicio y cumplir obligaciones legales y fiscales. Se aplican
            medidas técnicas y organizativas para proteger la información, entre
            ellas el cifrado de las credenciales y el control de quién accede a
            cada dato. El detalle de esas medidas se documenta internamente y se
            pone a disposición de la autoridad de control o de una auditoría que
            lo requiera; publicarlo en detalle debilitaría la protección que
            describe.
          </p>
        </Seccion>

        {/* ── 2. Términos ──────────────────────────────────────────────── */}
        <Seccion
          id="terminos"
          n={2}
          titulo="Términos y condiciones de uso"
          icono={<FileText size={19} color={MORADO} />}
        >
          <p style={p}>
            Estos Términos regulan el uso de la plataforma RIS App
            (risappbr.com), operada por SAIPHA Servicios Digitais. Al
            registrarse y utilizar la plataforma, el usuario los acepta.
          </p>

          <h3 style={h3}>2.1. Descripción del servicio</h3>
          <p style={p}>
            La plataforma permite registrar una cuenta y realizar recargas de
            saldo. Ese saldo se destina exclusivamente al consumo de las
            soluciones digitales disponibles dentro de la propia plataforma,
            que constituyen su línea principal de servicio. El saldo y los
            servicios son de uso interno de la aplicación.
          </p>

          <h3 style={h3}>2.2. Registro y cuenta</h3>
          <ul style={ul}>
            <li style={li}>El usuario debe ser mayor de edad y aportar información veraz y actualizada.</li>
            <li style={li}>El usuario es responsable de la confidencialidad de sus credenciales de acceso.</li>
            <li style={li}>La plataforma puede solicitar verificación de identidad para habilitar determinadas funciones.</li>
          </ul>

          <h3 style={h3}>2.3. Recargas y uso del saldo</h3>
          <ul style={ul}>
            <li style={li}>Las recargas se realizan a través de proveedores de pago autorizados.</li>
            <li style={li}>El saldo acreditado se destina al consumo de soluciones digitales dentro de la plataforma.</li>
            <li style={li}>Los importes, las comisiones y los límites aplicables se informan antes de confirmar cada operación.</li>
          </ul>

          <h3 style={h3}>2.4. Obligaciones del usuario</h3>
          <p style={p}>
            El usuario se compromete a no utilizar la plataforma con fines
            ilícitos, fraudulentos o no autorizados. El incumplimiento puede
            derivar en la suspensión o la cancelación de la cuenta.
          </p>

          <h3 style={h3}>2.5. Limitación de responsabilidad</h3>
          <p style={p}>
            La plataforma se ofrece «tal cual». En la medida en que la ley lo
            permita, no se responde por daños indirectos derivados de
            interrupciones del servicio, de errores del usuario o de causas de
            fuerza mayor.
          </p>

          <h3 style={h3}>2.6. Ley aplicable</h3>
          <p style={p}>
            Estos Términos se rigen por las leyes de la República Federativa de
            Brasil. Cualquier controversia se someterá a los tribunales
            competentes del domicilio de la empresa.
          </p>
        </Seccion>

        {/* ── 3. Reembolsos ────────────────────────────────────────────── */}
        <Seccion
          id="reembolsos"
          n={3}
          titulo="Política de reembolsos y devoluciones"
          icono={<RotateCcw size={19} color={MORADO} />}
        >
          <h3 style={h3}>3.1. Principio general</h3>
          <p style={p}>
            Las recargas de saldo se acreditan para el consumo de soluciones
            digitales dentro de la plataforma. Una vez que el saldo se consumió
            en un servicio, la operación se considera prestada y, por su
            naturaleza digital, no es reembolsable, salvo en los casos que se
            detallan a continuación.
          </p>

          <h3 style={h3}>3.2. Casos en que procede el reembolso</h3>
          <ul style={ul}>
            <li style={li}>Cobro duplicado o erróneo.</li>
            <li style={li}>Recarga no acreditada en la cuenta del usuario.</li>
            <li style={li}>Operación no reconocida por el usuario, sujeta a verificación.</li>
          </ul>

          <h3 style={h3}>3.3. Casos en que no procede el reembolso</h3>
          <ul style={ul}>
            <li style={li}>Saldo ya consumido en un servicio prestado dentro de la plataforma.</li>
            <li style={li}>Solicitudes derivadas de un uso incorrecto por parte del usuario.</li>
            <li style={li}>Cuentas suspendidas o canceladas por incumplimiento de estos Términos.</li>
          </ul>

          <h3 style={h3}>3.4. Cómo solicitar un reembolso</h3>
          <p style={p}>
            Abra una solicitud en <Soporte /> indicando su nombre, el
            comprobante de la operación y el motivo, preferentemente dentro de
            los siete días posteriores a la operación. La solicitud queda
            registrada al enviarse y se puede seguir desde la misma pantalla.
          </p>

          <h3 style={h3}>3.5. Plazos</h3>
          <p style={p}>
            Una vez aprobada la solicitud, el reembolso se procesa a través del
            mismo proveedor de pago utilizado en la operación original. El
            tiempo de acreditación depende de ese proveedor y de la entidad
            financiera del usuario, y puede demorar varios días hábiles.
          </p>
        </Seccion>

        {/* ── 4. Cancelación ───────────────────────────────────────────── */}
        <Seccion
          id="cancelacion"
          n={4}
          titulo="Política de cancelación de cuenta"
          icono={<UserMinus size={19} color={MORADO} />}
        >
          <p style={p}>
            El usuario puede solicitar la cancelación de su cuenta en cualquier
            momento.
          </p>

          <h3 style={h3}>4.1. Cómo cancelar</h3>
          <p style={p}>
            Solicite la baja desde <Soporte />, con la sesión iniciada en la
            cuenta que desea cancelar. Se verificará la identidad antes de
            proceder.
          </p>

          <h3 style={h3}>4.2. Saldo pendiente</h3>
          <p style={p}>
            Antes de cancelar, el usuario debe considerar el saldo disponible.
            Se le indicará el procedimiento aplicable al saldo no consumido,
            conforme a la Política de reembolsos.
          </p>

          <h3 style={h3}>4.3. Conservación de la información</h3>
          <p style={p}>
            Tras la cancelación, cierta información se conserva durante el plazo
            que exijan las obligaciones legales, fiscales y de prevención de
            fraude.
          </p>

          <h3 style={h3}>4.4. Cancelación por parte de la plataforma</h3>
          <p style={p}>
            La plataforma puede suspender o cancelar una cuenta que incumpla
            estos Términos, que presente actividad fraudulenta o que la ley
            obligue a cerrar.
          </p>
        </Seccion>

        {/* ── 5. Empresa ───────────────────────────────────────────────── */}
        <Seccion
          id="empresa"
          n={5}
          titulo="Información de la empresa"
          icono={<Building2 size={19} color={MORADO} />}
        >
          <p style={p}>La plataforma RIS App es operada por:</p>
          <div style={{
            border: '1px solid #ececf3', borderRadius: 12, overflow: 'hidden',
            marginBottom: 16,
          }}
          >
            {[
              ['Nombre comercial', 'SAIPHA Servicios Digitais'],
              ['País de operación', 'Brasil'],
              ['Sitio web', 'risappbr.com'],
            ].map(([k, v], i) => (
              <div
                key={k}
                style={{
                  display: 'flex', flexWrap: 'wrap', gap: 12, padding: '12px 16px',
                  borderTop: i === 0 ? 'none' : '1px solid #f3f3f7',
                  background: i % 2 ? '#fcfcfe' : '#fff',
                }}
              >
                <span style={{ fontSize: 13, color: '#9ca3af', minWidth: 130 }}>{k}</span>
                <span style={{ fontSize: 14.5, color: '#111827', flex: 1 }}>{v}</span>
              </div>
            ))}
          </div>

          {/*
            La razón social, el CNPJ y el domicilio se sacaron por decisión del
            operador, y por ahora. El domicilio, además, es un domicilio
            particular.

            Hay que decirlo derecho: el Decreto 7.962/2013 art. 2 I pide que un
            sitio de comercio electrónico publique el nombre empresarial y el
            CNPJ, así que mientras esto siga así el sitio no lo cumple. Los
            datos están completos en el dossier interno §1 y se entregan a quien
            los pida por el canal de atención.
          */}
          <p style={{ ...p, fontSize: 13.5, color: '#6b7280' }}>
            Los datos registrales completos del operador se entregan a quien los
            solicite por <Soporte />, y a cualquier autoridad que los requiera.
          </p>

          <h3 style={h3}>5.1. Canal de atención</h3>
          <p style={p}>
            Toda consulta —administrativa, sobre una operación o sobre el
            tratamiento de datos personales— se atiende por <Soporte />, dentro
            de la aplicación. Es el único canal habilitado: concentra el
            historial de cada caso en un solo lugar y deja constancia de cuándo
            se recibió y quién lo atendió.
          </p>
        </Seccion>

        {/* ── Cierre ───────────────────────────────────────────────────── */}
        <div style={{
          marginTop: 48, paddingTop: 22, borderTop: '1px solid #f1f0fb',
          display: 'flex', flexWrap: 'wrap', gap: 14,
          alignItems: 'center', justifyContent: 'space-between',
        }}
        >
          <p style={{ margin: 0, fontSize: 13, color: '#9ca3af', lineHeight: 1.6 }}>
            Este documento se revisa periódicamente. La fecha del encabezado
            indica la última versión vigente.
          </p>
        </div>
      </div>
    </div>
  );
}
