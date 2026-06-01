/**
 * Date helpers - relative + absolute formatting in Spanish.
 */

export function parseDate(input) {
  if (!input) return null;
  if (input instanceof Date) return input;
  const d = new Date(input);
  return isNaN(d.getTime()) ? null : d;
}

export function formatRelativeTime(input) {
  const d = parseDate(input);
  if (!d) return '—';
  const now = Date.now();
  let diffMs = now - d.getTime();
  const future = diffMs < 0;
  diffMs = Math.abs(diffMs);

  const sec = Math.round(diffMs / 1000);
  if (sec < 45) return future ? 'en unos segundos' : 'hace unos segundos';
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
  if (mo < 12) return future ? `en ${mo} meses` : `hace ${mo} meses`;
  const yr = Math.round(day / 365);
  return future ? `en ${yr} años` : `hace ${yr} años`;
}

export function formatAbsoluteTime(input) {
  const d = parseDate(input);
  if (!d) return '—';
  try {
    return d.toLocaleString('es-ES', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  } catch {
    return d.toISOString();
  }
}

export function formatShortDate(input) {
  const d = parseDate(input);
  if (!d) return '—';
  try {
    return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return d.toISOString().slice(0, 10);
  }
}
