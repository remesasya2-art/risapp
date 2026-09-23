/**
 * useComprobante — el comprobante de una operación, pedido al tocar el ojito.
 *
 * POR QUE SE PIDE APARTE
 *
 *   Las fotos se guardan adentro de la operación, en base64: unos 667 KB cada
 *   una, y un retiro completado lleva dos o más. La lista del historial las
 *   mandaba todas para dibujar un ojito: 10 MB cada vez que el cliente abría
 *   el inicio, con diez operaciones con foto. Ahora la lista dice sólo SI hay
 *   comprobante (`tiene_comprobante`) y las fotos se piden acá, por el detalle
 *   de esa operación.
 *
 * POR QUE UN SOLO LUGAR
 *
 *   El inicio y el historial abren el mismo comprobante. Ya tenían la misma
 *   normalización copiada dos veces; con el pedido al servidor, el estado de
 *   carga y el caso de error, dos copias terminan diciendo cosas distintas.
 *
 * POR QUE SE MIRA QUE LA RESPUESTA SEA LA ULTIMA QUE SE PIDIO
 *
 *   Si el cliente abre un comprobante, lo cierra y abre otro antes de que
 *   llegue el primero, la respuesta vieja pisaría a la nueva y le mostraría
 *   las fotos de OTRA operación bajo el título de ésta.
 */
import { useRef, useState } from 'react';
import api from '../utils/api';

// Las remesas BTC guardan el comprobante en 'comprobante_pago'; el modal
// muestra proof_image/proof_images, así que lo normalizamos aquí.
function normalizar(tx) {
  const normalized = { ...tx };
  const sinProof = !normalized.proof_image && (!normalized.proof_images || normalized.proof_images.length === 0);
  if (sinProof && normalized.comprobante_pago) {
    normalized.proof_image = normalized.comprobante_pago;
  }
  return normalized;
}

export default function useComprobante() {
  const [showVoucherModal, setShowVoucherModal] = useState(false);
  const [selectedVoucher, setSelectedVoucher] = useState(null);
  // 'cargando' | 'listo' | 'error'
  const [estadoDelComprobante, setEstadoDelComprobante] = useState('listo');
  const pedido = useRef(null);

  const openVoucher = async (deLaLista) => {
    const id = deLaLista.transaction_id;
    pedido.current = id;
    // El modal se abre enseguida, con lo que ya se sabe de la lista, para que
    // el toque tenga respuesta aunque las fotos tarden en llegar.
    setSelectedVoucher(normalizar(deLaLista));
    setEstadoDelComprobante('cargando');
    setShowVoucherModal(true);
    try {
      const { data } = await api.get(`/transactions/${encodeURIComponent(id)}`);
      if (pedido.current !== id) return;
      setSelectedVoucher(normalizar(data));
      setEstadoDelComprobante('listo');
    } catch {
      if (pedido.current === id) setEstadoDelComprobante('error');
    }
  };

  return { showVoucherModal, setShowVoucherModal, selectedVoucher, openVoucher, estadoDelComprobante };
}
