/**
 * Format a number as `1.000.000,00` (Latin/European: dot thousands, comma decimals)
 * @param {number|string} n - Value to format
 * @param {number} d - Decimals (default: 2)
 * @returns {string}
 */
export const fmt = (n, d = 2) => {
  if (n === null || n === undefined || n === '' || isNaN(n)) return '0,00';
  return Number(n).toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d });
};

/**
 * Group an account number into chunks of 4 digits: 0115 1234 5678 9854 8884
 */
export const formatAccountNumber = (acc) => {
  if (!acc) return '';
  const digits = String(acc).replace(/\D/g, '');
  return digits.replace(/(\d{4})(?=\d)/g, '$1 ').trim();
};

/**
 * Spanish relative time: "hace 5 min", "hace 2 h", "ayer", "hace 3 días".
 */
export const fmtRelative = (input) => {
  if (!input) return '';
  const d = input instanceof Date ? input : new Date(input);
  if (isNaN(d.getTime())) return '';
  let diffMs = Date.now() - d.getTime();
  const future = diffMs < 0;
  diffMs = Math.abs(diffMs);
  const sec = Math.round(diffMs / 1000);
  if (sec < 60) return future ? 'en unos seg' : 'hace unos seg';
  const min = Math.round(sec / 60);
  if (min < 60) return future ? `en ${min} min` : `hace ${min} min`;
  const hr = Math.round(min / 60);
  if (hr < 24) return future ? `en ${hr} h` : `hace ${hr} h`;
  const day = Math.round(hr / 24);
  if (day === 1) return future ? 'mañana' : 'ayer';
  if (day < 7) return future ? `en ${day} días` : `hace ${day} días`;
  const wk = Math.round(day / 7);
  if (wk < 5) return future ? `en ${wk} sem` : `hace ${wk} sem`;
  const mo = Math.round(day / 30);
  return future ? `en ${mo} meses` : `hace ${mo} meses`;
};
