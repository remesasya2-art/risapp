/**
 * Comisiones de red estimadas por ticker de NOWPayments, expresadas en la
 * propia cripto (USDT / USDC, o sea ~USD).
 *
 * De donde salen estos numeros: son mediciones reales de pagos que quedaron en
 * estado "Finished" en NOWPayments durante agosto de 2026. NO son un contrato
 * ni un valor que NOWPayments garantice: el costo real de cada transferencia se
 * mueve con la congestion de la red. Sirven para que el usuario tenga el orden
 * de magnitud antes de generar el pago, nada mas.
 *
 * Cualquier ticker que no este en esta tabla no muestra numero: se cae al texto
 * de UNKNOWN_NETWORK_FEE_TEXT ("se confirma al generar el pago").
 */
export const ESTIMATED_NETWORK_FEE = {
  usdttrc20: 0.03,
  usdtbsc: 0.08,
  usdtmatic: 0.08,
  usdtsol: 0.31,
  usdcbsc: 0.02,
  usdc: 0.38,      // ERC20 (ticker default de USDC)
  usdterc20: 0.38, // mismo gas que ERC20-USDC, mismo tipo de transferencia
};

/** Texto para las redes de las que todavia no tenemos una medicion propia. */
export const UNKNOWN_NETWORK_FEE_TEXT = 'se confirma al generar el pago';

/** Comision de servicio de NOWPayments sobre el monto enviado (~1%). */
export const NOWPAYMENTS_FEE_RATE = 0.01;

/**
 * Comision de red estimada para un ticker, o null si no la tenemos medida.
 * El caller decide que mostrar cuando es null (ver UNKNOWN_NETWORK_FEE_TEXT).
 */
export function estimatedNetworkFee(ticker) {
  if (!ticker) return null;
  const fee = ESTIMATED_NETWORK_FEE[String(ticker).toLowerCase()];
  return typeof fee === 'number' ? fee : null;
}
