// Lo que muestra la ventana del comprobante mientras las fotos no llegaron, o
// si no llegaron. Sin esto, mientras cargan se leería «No hay comprobante
// disponible», que es justo lo que el cliente no tiene que creer.
export default function AvisoDelComprobante({ estado }) {
  const texto = estado === 'cargando'
    ? 'Cargando comprobante…'
    : 'No se pudo cargar el comprobante. Cerrá esta ventana y probá de nuevo.';
  return (
    <div
      data-testid={`comprobante-${estado}`}
      style={{
        padding: '40px', backgroundColor: '#f9fafb', borderRadius: '12px',
        textAlign: 'center', border: '1px dashed #d1d5db',
      }}
    >
      <p style={{ color: estado === 'error' ? '#dc2626' : '#6b7280', margin: 0, fontSize: '14px' }}>{texto}</p>
    </div>
  );
}
