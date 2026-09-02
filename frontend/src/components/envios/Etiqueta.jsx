/**
 * Etiqueta.jsx — La dirección que el usuario copia sobre la caja.
 *
 * La arma el SERVIDOR, con la misma función que usa la cotización, y queda
 * congelada en el envío: tiene que decir lo mismo cuando el usuario vuelve a
 * mirarla, aunque después haya cambiado quién está de turno en Pacaraima.
 *
 * Vive acá y no adentro de una página porque la usan dos: la cotización y el
 * detalle. Importarla de página a página arrastraba el módulo entero de una al
 * chunk de la otra.
 */
import toast from 'react-hot-toast';
import { Copy } from 'lucide-react';
import { Boton } from './ui';
import { bajada, tarjeta, titulo } from './estilos';

/**
 * @param previa  Mostrarla ANTES de confirmar, como información y no como
 *   instrucción. Se ve el mismo texto —quien retira, la agencia, el CEP— pero
 *   sin el botón de copiar y sin el «rotulá la caja así».
 *
 *   La diferencia no es cosmética. Que el usuario vea a nombre de quién va a
 *   despachar ANTES de comprometerse es lo que esta variante viene a resolver:
 *   confirmar sin haberlo visto es aceptar mandar una caja a un nombre
 *   desconocido. Pero entregarle acá el texto listo para copiar reabre un
 *   incidente ya conocido — alguien lo copia, va a despachar, no confirma
 *   nunca, y a las 48 h la cotización se borra sola por TTL y la caja llega a
 *   Pacaraima sin ningún envío que la reclame.
 *
 *   Por eso el texto se VE y no se ACCIONA: la etiqueta para copiar aparece en
 *   el detalle del envío, que es la pantalla a la que se llega al confirmar.
 */
export default function Etiqueta({ retiro, previa = false }) {
  if (!retiro?.texto_copiable) return null;
  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(retiro.texto_copiable);
      toast.success('Copiado');
    } catch {
      toast.error('El navegador no dejó copiar. Seleccionalo a mano.');
    }
  };
  return (
    <div style={{ ...tarjeta, backgroundColor: '#0f172a', borderColor: '#0f172a' }}>
      <h3 style={{ ...titulo, color: '#fff' }}>
        {previa ? 'A dónde vas a despachar' : 'Rotulá la caja así'}
      </h3>
      <p style={{ ...bajada, color: '#94a3b8' }}>
        {previa
          ? 'Esto es lo que vas a rotular sobre la caja. Mirá el nombre: en el mostrador de Pacaraima lo comparan contra un documento, y si no coincide no la entregan.'
          : 'Copiá esto tal cual sobre la caja. En el mostrador de Pacaraima comparan esta etiqueta contra un documento: si el nombre no coincide, no la entregan.'}
      </p>
      <pre style={{ margin: 0, padding: '16px', borderRadius: '12px',
        backgroundColor: '#1e293b', color: '#e2e8f0', fontSize: '14px', lineHeight: 1.7,
        whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'monospace' }}>
        {retiro.texto_copiable}
      </pre>
      {previa ? (
        <p style={{ margin: '12px 0 0 0', fontSize: '13px', color: '#fbbf24' }}>
          Todavía no despaches. Confirmá el envío acá abajo primero: si mandás la caja sin
          confirmar, esta cotización vence en 48 horas y el paquete llega a Pacaraima sin
          ningún envío que lo reclame.
        </p>
      ) : (
        <Boton variante="secundario" style={{ marginTop: '12px' }} onClick={copiar}>
          <Copy size={14} /> Copiar
        </Boton>
      )}
    </div>
  );
}
