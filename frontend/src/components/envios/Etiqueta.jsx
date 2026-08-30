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

export default function Etiqueta({ retiro }) {
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
      <h3 style={{ ...titulo, color: '#fff' }}>Rotulá la caja así</h3>
      <p style={{ ...bajada, color: '#94a3b8' }}>
        Copiá esto tal cual sobre la caja. En el mostrador de Pacaraima comparan esta
        etiqueta contra un documento: si el nombre no coincide, no la entregan.
      </p>
      <pre style={{ margin: 0, padding: '16px', borderRadius: '12px',
        backgroundColor: '#1e293b', color: '#e2e8f0', fontSize: '14px', lineHeight: 1.7,
        whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'monospace' }}>
        {retiro.texto_copiable}
      </pre>
      <Boton variante="secundario" style={{ marginTop: '12px' }} onClick={copiar}>
        <Copy size={14} /> Copiar
      </Boton>
    </div>
  );
}
