/**
 * components/MiCodigoDeReferido.jsx — El enlace para invitar, donde se vea.
 *
 * POR QUE EXISTE ESTA TARJETA
 *
 *   Cada usuario recibe un código de invitación al registrarse. Eso ya pasaba
 *   desde siempre, y la ruta que lo devuelve —`GET /referidos/mi-codigo`—
 *   también existía. Lo que no existía era una pantalla que lo mostrara, así
 *   que el código estaba guardado en la base y no había forma de verlo.
 *
 *   Un enlace que nadie puede ver es un enlace que nadie comparte.
 *
 * LO QUE ESTA TARJETA NO DICE, A PROPOSITO
 *
 *   No dice cuánto se gana. El bono ya existe, pero sus montos se configuran
 *   desde el panel del super administrador y pueden cambiar cualquier día: un
 *   «ganá 5 R$» escrito acá sería un número que se desactualiza solo, y el
 *   primero en enterarse sería un cliente reclamando.
 *
 *   Para citarlos hace falta que el servidor los mande —hoy el catálogo de
 *   configuración es sólo del super administrador—, y eso es un cambio con su
 *   propia decisión: qué valores se hacen públicos y cuáles no.
 *
 *   Lo que la persona sí puede ver es lo que ya cobró y lo que le falta, en
 *   «A quién invité».
 *
 * POR QUE NO SE DIBUJA NADA SI NO HAY CODIGO
 *
 *   Una cuenta vieja puede no tenerlo, y la ruta devuelve vacío en ese caso a
 *   propósito (está explicado en `routes/referidos.py`: generarlo al leerlo
 *   crearía dos códigos distintos en dos pedidos simultáneos). Una tarjeta con
 *   el hueco en blanco se ve como un error de la aplicación; no dibujar nada
 *   se ve como que esa cuenta no tiene esta función, que es la verdad.
 */
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight, Copy, Gift, Share2, Users } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../utils/api';
import { Boton } from './flujo';
import { C, tarjeta, microEtiqueta } from './flujo/estilos';

export default function MiCodigoDeReferido() {
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const r = await api.get('/referidos/mi-codigo');
        if (vivo) setDatos(r.data);
      } catch {
        // Sin toast: esta tarjeta es un extra de la pantalla de perfil, y un
        // cartel rojo por no poder leer un enlace para compartir asusta más
        // de lo que informa. La tarjeta no se dibuja y listo.
        if (vivo) setDatos(null);
      } finally {
        if (vivo) setCargando(false);
      }
    })();
    // La bandera evita escribir estado sobre un componente ya desmontado, que
    // es lo que pasa si alguien entra al perfil y se va antes de que responda.
    return () => { vivo = false; };
  }, []);

  if (cargando || !datos?.codigo) return null;

  const copiar = async (texto, queEs) => {
    try {
      await navigator.clipboard.writeText(texto);
      toast.success(`${queEs} copiado`);
    } catch {
      // `navigator.clipboard` falla sin permiso, y en algunos navegadores de
      // teléfono directamente no está. El texto se ve en pantalla, así que
      // siempre queda la salida de seleccionarlo a mano.
      toast.error('El navegador no dejó copiar. Seleccionalo a mano.');
    }
  };

  const compartir = async () => {
    try {
      await navigator.share({
        title: 'RIS App',
        text: 'Mandá plata a Venezuela con RIS App. Entrá con mi invitación:',
        url: datos.enlace,
      });
    } catch {
      // Cancelar la hoja de compartir también llega acá como un rechazo, y
      // avisarle «falló» a quien decidió no compartir es mentirle. Silencio.
    }
  };

  return (
    <section data-testid="mi-codigo-de-referido"
      style={{ ...tarjeta, padding: '18px 20px', marginBottom: '16px' }}>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <span style={{
          width: '38px', height: '38px', borderRadius: '11px', flexShrink: 0,
          background: C.marcaSuave,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Gift size={18} color={C.marca} />
        </span>
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: 'block', fontSize: '14.5px', fontWeight: 600, color: C.tinta }}>
            Invitá a quien quieras
          </span>
          <span style={{ display: 'block', fontSize: '12.5px', color: C.suave, marginTop: '1px' }}>
            Quien se registre con tu enlace queda ligado a tu cuenta
          </span>
        </span>
      </div>

      {/* ── El código ──────────────────────────────────────────────────── */}
      <div style={{ marginTop: '15px' }}>
        <span style={microEtiqueta}>Tu código</span>
        <button type="button" onClick={() => copiar(datos.codigo, 'Código')}
          className="env-tap" data-testid="copiar-codigo-referido"
          style={{
            marginTop: '6px', width: '100%', height: '52px', padding: '0 16px',
            borderRadius: '12px', border: `1px solid ${C.lineaFuerte}`,
            background: C.fondo, cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            gap: '12px',
          }}>
          <span style={{
            fontSize: '19px', fontWeight: 700, color: C.tinta,
            letterSpacing: '.06em', fontVariantNumeric: 'tabular-nums',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {datos.codigo}
          </span>
          <Copy size={17} color={C.suave} style={{ flexShrink: 0 }} />
        </button>
      </div>

      {/* ── A quién invité ─────────────────────────────────────────────── */}
      {/* Debajo del código y arriba del enlace: quien ya invitó a alguien
          entra acá a ver cómo le fue, y quien todavía no lo hizo tiene el
          enlace a un dedo de distancia. */}
      <Link to="/referidos" data-testid="ver-mis-referidos"
        className="env-tap"
        style={{
          marginTop: '13px', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', gap: '10px',
          height: '46px', padding: '0 14px', borderRadius: '11px',
          border: `1px solid ${C.linea}`, background: C.lienzo,
          textDecoration: 'none',
        }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '9px' }}>
          <Users size={16} color={C.suave} />
          <span style={{ fontSize: '14px', fontWeight: 600, color: C.tinta }}>
            A quién invité
          </span>
        </span>
        <ChevronRight size={17} color={C.tenue} />
      </Link>

      {/* ── El enlace ──────────────────────────────────────────────────── */}
      {datos.enlace ? (
        <div style={{ marginTop: '13px' }}>
          <span style={microEtiqueta}>Tu enlace</span>
          {/* Se muestra completo y se corta con puntos suspensivos si no
              entra. Un enlace recortado con «...» en el medio no se puede
              leer en voz alta por teléfono, que es como se comparte cuando
              el que invita y el invitado están hablando. */}
          <p data-testid="enlace-referido" style={{
            margin: '6px 0 0', padding: '11px 13px', borderRadius: '10px',
            border: `1px solid ${C.linea}`, background: C.fondo,
            fontSize: '12.5px', color: C.texto, wordBreak: 'break-all',
          }}>
            {datos.enlace}
          </p>

          <div style={{ display: 'flex', gap: '9px', marginTop: '11px' }}>
            <Boton onClick={() => copiar(datos.enlace, 'Enlace')} Icono={Copy}
              ancho testid="copiar-enlace-referido">
              Copiar enlace
            </Boton>
            {/* `navigator.share` existe casi sólo en teléfonos. En una
                computadora el botón no se dibuja en vez de dibujarse y
                fallar al tocarlo. */}
            {typeof navigator !== 'undefined' && navigator.share ? (
              <Boton onClick={compartir} tipo="primario" Icono={Share2}
                ancho testid="compartir-enlace-referido">
                Compartir
              </Boton>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
