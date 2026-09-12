/**
 * components/dashboard/BonoCard.jsx — El bono de bienvenida, cuando hay.
 *
 * POR QUE UNA TARJETA APARTE Y NO UN NUMERO DENTRO DEL SALDO
 *
 *   Porque es un saldo aparte, con reglas propias: está bloqueado hasta que se
 *   apruebe la verificación de identidad, y después se gasta SOLO en envíos a
 *   Venezuela. Sumarlo al saldo principal diría una mentira —que se puede usar
 *   para cualquier cosa— y esconder la única condición que importa.
 *
 *   Es el mismo criterio que ya usa `CryptoBalanceCard`: un saldo con reglas
 *   distintas se muestra en su propia tarjeta.
 *
 * EL TEXTO LO ESCRIBE EL SERVIDOR
 *
 *   `leyenda` viene de `services/bonos.para_la_pantalla`. Si el texto se
 *   armara acá, el monto y la condición podrían discrepar entre los dos lados,
 *   y el que se equivoca es siempre el que no se actualizó.
 *
 * SI NO HAY BONO NO SE DIBUJA NADA
 *
 *   Ni un cero, ni un cartel de «no tenés bono». Un cero permanente en el
 *   panel invita a preguntar por qué es cero, y la respuesta es «porque no te
 *   registraste con un código», que no es algo que se pueda arreglar.
 */
import { Gift, Lock } from 'lucide-react';

export default function BonoCard({ bono, isMobile = false }) {
  if (!bono?.tiene) return null;

  const bloqueado = Boolean(bono.bloqueado);
  // Lo que manda el servidor es texto, que es como viaja la plata por el
  // borde del API. Se formatea para leer, sin volver a calcular nada.
  const monto = Number(bono.saldo || 0).toLocaleString('pt-BR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });

  const acento = bloqueado ? '#B54708' : '#067647';
  const fondo = bloqueado ? '#FFFAEB' : '#ECFDF3';
  const borde = bloqueado ? '#FEDF89' : '#A9EFC5';

  return (
    <div data-testid="bono-card" style={{
      backgroundColor: '#ffffff', borderRadius: '16px',
      padding: isMobile ? '16px' : '18px 20px',
      border: '1px solid #eef0f4', boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
      display: 'flex', alignItems: 'flex-start', gap: '14px',
    }}>
      <span style={{
        width: '40px', height: '40px', borderRadius: '12px', flexShrink: 0,
        backgroundColor: fondo, border: `1px solid ${borde}`,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {bloqueado ? <Lock size={18} color={acento} />
                   : <Gift size={18} color={acento} />}
      </span>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'wrap',
        }}>
          <span style={{
            fontSize: '13px', fontWeight: 600, color: '#6b7280',
          }}>
            Bono de bienvenida
          </span>
          {bloqueado ? (
            <span data-testid="bono-bloqueado" style={{
              fontSize: '11px', fontWeight: 700, color: acento,
              backgroundColor: fondo, border: `1px solid ${borde}`,
              borderRadius: '9999px', padding: '2px 8px',
            }}>
              BLOQUEADO
            </span>
          ) : (
            <span data-testid="bono-disponible" style={{
              fontSize: '11px', fontWeight: 700, color: acento,
              backgroundColor: fondo, border: `1px solid ${borde}`,
              borderRadius: '9999px', padding: '2px 8px',
            }}>
              DISPONIBLE
            </span>
          )}
        </div>

        <div style={{
          fontSize: '24px', fontWeight: 700, color: '#111827',
          fontVariantNumeric: 'tabular-nums', marginTop: '2px',
        }}>
          R$ {monto}
        </div>

        <p style={{
          margin: '4px 0 0', fontSize: '12.5px', color: '#6b7280',
          lineHeight: 1.5,
        }}>
          {bono.leyenda}
        </p>
      </div>
    </div>
  );
}
