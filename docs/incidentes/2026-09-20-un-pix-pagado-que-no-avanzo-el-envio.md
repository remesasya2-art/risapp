# Un PIX pagado que no hizo avanzar el envío

**Fecha del reporte:** 20 de septiembre de 2026
**Lo reportó:** el dueño del proyecto, desde producción
**Estado:** arreglado. El receptor de avisos de Mercado Pago busca el cobro con los
dos tipos de identificador (`routes/gestor_pix.py`, `pago_que_no_se_acredito.identificadores_posibles`),
y los avisos que no encuentran su cobro quedan en la pantalla «Cobros sin acreditar» en vez
de perderse. Lo que sigue pendiente es lo de la orden concreta del cliente, más abajo,
que es un trabajo a mano y no de código.

---

## Qué pasó, en una línea

Un cliente pagó su envío con PIX y la orden se quedó en «esperando pago».

## Qué se sabe con certeza

- El cliente pagó. La plata salió de su cuenta.
- La orden no avanzó en la aplicación.
- La hipótesis del dueño al reportarlo fue: «¿será que no recibió la llamada
  de Mercado Pago?».

## Qué encontré

**Mercado Pago probablemente sí llamó. La llamada llegó y no encontró el
cobro**, por una diferencia de tipos entre cómo se guarda el identificador y
cómo se busca.

### La causa

Al crear el cobro, `mercadopago_service.py:81` guarda lo que devuelve el SDK:

```python
payment_id = response.get("id")     # un ENTERO: 123456789
```

y eso queda en `gestor_pix_payments.mp_payment_id`.

Al recibir el aviso, `routes/gestor_pix.py:114` lee lo que manda Mercado Pago
en el cuerpo del webhook:

```python
mp_payment_id = data.get("id")      # una CADENA: "123456789"
```

y busca con eso, sin convertir (`gestor_pix.py:126`):

```python
payment = await db.gestor_pix_payments.find_one({
    "mp_payment_id": mp_payment_id
})
```

MongoDB no iguala `123456789` con `"123456789"`. La búsqueda no encuentra
nada, el webhook contesta `payment_not_found` **con un 200**, y la orden no se
toca.

Comprobado ejecutándolo contra una base:

```
buscando la cadena  -> NO ENCUENTRA NADA
buscando el entero  -> ENCONTRADO
```

### La prueba de que esto ya se sabía, a medias

Doce líneas más abajo, en el mismo archivo, el camino de las tarjetas **sí**
convierte (`gestor_pix.py:132`):

```python
card_payment = await db.card_payments.find_one({"payment_id": str(mp_payment_id)})
```

Alguien se topó con esto en el camino de la tarjeta y lo arregló ahí. El de
PIX quedó como estaba.

## Por qué no se había notado antes

Porque **las recargas tienen una segunda red y los envíos no.**

`Recharge.jsx` pregunta cada pocos segundos por su cuenta
(`GET /gestor/pix/status/{id}`, línea 191). Mientras el cliente mira la
pantalla, esa consulta acredita el pago aunque el webhook no haya servido de
nada. El webhook viene fallando, pero el sondeo lo tapa.

`Send.jsx` —el envío que cobra al final— **no pregunta nunca**. Su único
temporizador es el que refresca la tasa. Así que ese flujo depende
exclusivamente del webhook.

Eso lo dice, sin saberlo, el encabezado de la pantalla de administración que
existe justamente para este problema
(`frontend/src/components/admin/CobrosSinAcreditar.jsx`):

> Un pago de Mercado Pago se acredita por dos caminos —el aviso del servidor
> de Mercado Pago y la pantalla del cliente, que pregunta mientras espera— y
> quien PAGA Y CIERRA LA PANTALLA cae en el medio de los dos.

Lo que esa nota no dice es que **el primero de los dos caminos no funciona**,
y que para los envíos es el único que hay.

**Consecuencia:** ningún envío pagado con PIX se confirma solo. Ni uno. El
flujo que cobra al final se desplegó el 19 de septiembre, así que la ventana
es corta — pero dentro de esa ventana, todos.

## Lo que hay que mirar en producción para confirmarlo

1. En el registro del servidor, buscar la línea:

   ```
   Payment <id> not found in our database
   ```

   Si está, Mercado Pago llamó y la búsqueda falló. Confirma esto.

2. Si **no** hay ninguna línea de webhook para ese pago, entonces la llamada
   no llegó y la causa es otra —la hipótesis original del dueño—. En ese caso
   hay que mirar la configuración del webhook en Mercado Pago y el secreto de
   la firma.

3. Contar cuántos cobros quedaron colgados:

   ```
   transactions:  status = "awaiting_payment" o "payment_expired",
                  payment_order_id que empiece con "venv_"
   ```

   y cruzarlos contra Mercado Pago por su `payment_order_id`, que viaja como
   `external_reference`.

## Los otros seis lugares donde esto mismo pasa en silencio

El desajuste de tipos es la causa más probable, pero **no es la única puerta**.
Estos puntos de `mercadopago_webhook` devuelven 200 y no avisan a nadie:

| Línea | Qué pasa | Qué queda |
|---|---|---|
| 130 | no encuentra el cobro | un `WARNING` |
| 139 | el cobro no está en «pending» | un `INFO` |
| 144 | el servicio de Mercado Pago no está disponible | un `ERROR` |
| 151 | no se pudo reverificar contra Mercado Pago | un `ERROR` |
| 159 | el monto no coincide | un `ERROR` y el cobro marcado «suspicious» |
| 200 | la confirmación devolvió `False` | un `ERROR` |

Los seis terminan igual: **el cliente pagó y nadie se entera.** Ninguno avisa
al equipo, ninguno deja la orden en un estado que alguien vaya a mirar.

Que el webhook devuelva 200 en todos estos casos es correcto —si devolviera
error, Mercado Pago reintentaría eternamente—, pero eso hace que el silencio
sea total.

## Lo que hay que arreglar

En orden de urgencia:

1. **Comparar el identificador sin que el tipo importe.** Buscar por los dos,
   o guardarlo siempre como cadena. Es el arreglo de la causa.

2. **Que un webhook que no puede acreditar avise al equipo.** Es lo que
   convierte «el cliente pagó y nadie se entera» en «el cliente pagó y alguien
   lo ve en un minuto». Vale para los seis casos de la tabla, no sólo para
   éste.

3. **Que la pantalla del envío pregunte, como hace la de recarga.** No arregla
   la causa: le pone al envío la misma segunda red que tiene la recarga, para
   que el próximo fallo del webhook —del tipo que sea— no deje a nadie
   colgado.

4. **Revisar por qué `CobrosSinAcreditar` no encontró esto.** Existe para
   exactamente este problema. O no cubre los cobros con propósito de envío, o
   no se corre. Conviene saber cuál de las dos.

## Lo que hay que hacer con la orden del cliente

Es de una persona que ya pagó, así que no espera al arreglo:

1. Confirmar contra Mercado Pago que el pago está aprobado, por su
   `external_reference` (el `payment_order_id`, que empieza con `venv_`).
2. Hacer avanzar la orden a mano.
3. Anotarlo en el libro de auditoría.

Si la orden ya venció y el barrido la movió, el bono que se haya usado ya le
volvió a la cuenta: hay que descontarlo otra vez antes de despachar, o se
regala.

---

## Nota de método

La causa está **demostrada ejecutándola**, no deducida leyendo el código. Lo
que **no** está confirmado es que sea la causa de este caso concreto: para eso
hace falta el registro de producción, que desde el entorno de estas sesiones
no se puede leer.

Lo que sí es seguro: este defecto existe, produce exactamente este síntoma, y
afecta a todos los envíos pagados con PIX.
