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
