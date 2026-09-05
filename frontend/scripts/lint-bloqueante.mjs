/**
 * lint-bloqueante.mjs — Las reglas del frontend que sí frenan una entrega.
 *
 * POR QUE NO ALCANZA CON `npm run lint`
 *
 *   Hoy `eslint src/` reporta 151 errores. Casi todos son variables sin usar y
 *   avisos de estilo: deuda real, pero deuda que no rompe nada en pantalla.
 *   Poner eso como condición para entregar dejaría la rama roja para siempre,
 *   y una rama que siempre está roja no frena nada — se aprende a ignorarla.
 *
 *   Este script separa las dos cosas. Frena SOLO lo que ya sabemos que rompe
 *   la aplicación en producción, y deja el resto como información.
 *
 * QUE FRENA, Y POR QUE ESAS
 *
 *   - Un archivo que no parsea. No hay discusión: no compila.
 *
 *   - `react-hooks/rules-of-hooks`. Esta regla se ganó el lugar: en
 *     `AdminPanel.jsx` había un `useEffect` adentro de un manejador de
 *     eventos, por una llave mal puesta. La pestaña de órdenes BTC abría
 *     vacía —una orden pendiente que nadie ve es una persona esperando— y
 *     marcar una orden como enviada tiraba «Invalid hook call» justo después
 *     de haber mandado la plata. Compilaba, se desplegaba, y el aviso estaba
 *     perdido entre otros 150.
 *
 *   El resto se imprime y no frena. Cuando una categoría llegue a cero, el
 *   lugar para dejarla en cero es esta lista.
 */
import { execFileSync } from 'node:child_process';

const FRENAN = new Set(['react-hooks/rules-of-hooks']);

let salida;
try {
  salida = execFileSync(
    'npx',
    ['eslint', 'src/', '-f', 'json'],
    { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
  );
} catch (e) {
  // eslint sale con código 1 cuando encuentra errores: es lo esperado, y lo
  // que nos interesa viene igual por stdout. Si no vino nada, entonces sí
  // falló de verdad y hay que decirlo en vez de dar verde.
  salida = e.stdout;
  if (!salida) {
    console.error('No se pudo correr eslint:\n', e.stderr || e.message);
    process.exit(2);
  }
}

const archivos = JSON.parse(salida);
const graves = [];
const porRegla = new Map();

for (const archivo of archivos) {
  for (const m of archivo.messages) {
    const regla = m.ruleId || '(no parsea)';
    if (m.severity !== 2) continue;
    porRegla.set(regla, (porRegla.get(regla) || 0) + 1);
    if (FRENAN.has(regla) || m.ruleId === null) {
      graves.push(`${archivo.filePath}:${m.line}:${m.column}  ${regla}\n    ${m.message}`);
    }
  }
}

console.log('\n  Errores por regla (informativo):');
for (const [regla, n] of [...porRegla].sort((a, b) => b[1] - a[1])) {
  console.log(`    ${String(n).padStart(4)}  ${regla}${FRENAN.has(regla) ? '   ← FRENA' : ''}`);
}

if (!graves.length) {
  console.log('\n  Ninguna regla bloqueante incumplida.\n');
  process.exit(0);
}

console.log(`\n  ${graves.length} incumplimiento(s) de una regla que frena:\n`);
for (const g of graves) console.log(`    ${g}\n`);
console.log('  Estas reglas frenan porque cada una ya rompió la aplicación en');
console.log('  producción al menos una vez. Ver la cabecera de este archivo.\n');
process.exit(1);
