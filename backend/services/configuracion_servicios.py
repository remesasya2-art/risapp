"""
services/configuracion_servicios.py — Las llaves de cada servicio dentro del
catálogo de Configuración.

POR QUE ESTAN EN UN ARCHIVO APARTE

    Vivían en `AJUSTES`, adentro de `services/configuracion.py`, que llegó a
    808 líneas: su tope congelado en tests/archivos_largos.txt. Hacía falta
    una llave más —la de remesas— y el archivo no podía crecer ni una línea.
    Se movieron acá tal cual, con sus comentarios.

    Siguen siendo entradas del mismo catálogo: `configuracion.py` las suma en
    su lugar, en el mismo orden, así que la pantalla de Configuración, la
    validación, el API y quien las lee con `configuracion.leer` no cambian.

    Lo que cada llave corta y lo que deja andando está en el módulo de cada
    una: services/recarga_abierta.py, services/encomiendas_abiertas.py,
    services/cripto_abierta.py y nucleo/modo.py.
"""
from decimal import Decimal

from services.configuracion_ajuste import DINERO, ENTERO, Ajuste

AJUSTES_DE_LOS_SERVICIOS = {
    # ── Cargar saldo ──────────────────────────────────────────────────────
    #
    # La empresa no custodia dinero de terceros ni ofrece recarga. El estado al
    # que se va es 0; viene en 1 de fábrica porque el despliegue no puede ser
    # el que lo apague —los envíos exigen saldo, y se quedarían sin forma de
    # financiarse en ese mismo instante—. Hay una regla que impide apagarlo
    # antes de tiempo: ver `PAREJAS_MINIMO_Y_MAXIMO` y el seguro de
    # `services/recarga_abierta.py`.
    "recarga_abierta": Ajuste(
        tipo=ENTERO, defecto=1, minimo=0, maximo=1,
        unidad="0 = no se carga saldo, 1 = se puede cargar",
        etiqueta="Cargar saldo (PIX, tarjeta y bolívares)",
        ayuda="En 1 (fábrica) todo sigue igual. En 0 no entra saldo nuevo por "
              "ninguna de las tres vías, pero el saldo que ya está se sigue "
              "gastando y sigue recibiendo devoluciones. No se puede poner en "
              "0 mientras «pagar el envío al final» esté apagado: con los dos "
              "apagados nadie podría enviar nada."),

    # ── Encomiendas ───────────────────────────────────────────────────────
    #
    # El servicio de encomiendas se suspende por ahora. Viene en 1 de fábrica
    # por la misma regla que la recarga: el despliegue no apaga cosas solo, lo
    # apaga una persona desde acá. Qué se apaga y qué sigue andando está en
    # `services/encomiendas_abiertas.py`.
    "encomiendas_abiertas": Ajuste(
        tipo=ENTERO, defecto=1, minimo=0, maximo=1,
        unidad="0 = suspendido, 1 = se pueden mandar",
        etiqueta="Envío de paquetes (encomiendas)",
        ayuda="En 1 (fábrica) todo sigue igual. En 0 no se pueden cotizar ni "
              "confirmar encomiendas nuevas y el menú del cliente deja de "
              "ofrecerlas, pero las que ya están en camino siguen su curso: "
              "el cliente las ve, sube comprobantes y paga lo que deba, y el "
              "panel de Encomiendas sigue entero para terminarlas."),

    # ── El núcleo de cuentas ──────────────────────────────────────────────
    #
    # La arquitectura de fintech que se construye mientras se resuelve lo
    # legal. Viene APAGADA de fábrica y falla cerrado: sus rutas contestan
    # 404 a todo el mundo. En 1, sólo el super administrador ve la pestaña
    # «Núcleo» del panel, con datos de prueba; los clientes no ven nada. El 2
    # queda reservado para cuando haya licencia y HOY se comporta igual que
    # el 1. Ver `nucleo/modo.py`.
    "nucleo_modo": Ajuste(
        tipo=ENTERO, defecto=0, minimo=0, maximo=2,
        unidad="0 = apagado, 1 = laboratorio, 2 = activo (reservado)",
        etiqueta="Núcleo de cuentas (fintech)",
        ayuda="En 0 (fábrica) no existe: ni rutas ni pestaña. En 1 aparece la "
              "pestaña «Núcleo» sólo para el super administrador, con plata de "
              "prueba, y los clientes no ven nada. El 2 está reservado para el "
              "día que haya licencia; hoy hace lo mismo que el 1."),

    # LOS UMBRALES DEL MONITOREO DEL NUCLEO. Los lee `nucleo/riesgo/monitoreo.py`
    # cada vez que evalúa una operación; se cambian acá y rigen enseguida.
    # Están en el catálogo y no en código porque el oficial de cumplimiento
    # los va a ajustar más de una vez, y ninguno debería ser un despliegue.
    "nucleo_umbral_operacion": Ajuste(
        tipo=DINERO, defecto=Decimal("10000.00"), minimo=Decimal("100.00"), maximo=Decimal("1000000.00"),
        unidad="R$", etiqueta="Núcleo · umbral por operación",
        ayuda="Una operación por un riel del núcleo igual o mayor que esto deja "
              "una alerta de monitoreo y abre un caso. Sólo cuenta con el núcleo "
              "prendido; no toca los límites de la aplicación."),
    "nucleo_umbral_30_dias": Ajuste(
        tipo=DINERO, defecto=Decimal("50000.00"), minimo=Decimal("1000.00"), maximo=Decimal("10000000.00"),
        unidad="R$", etiqueta="Núcleo · acumulado en 30 días",
        ayuda="Lo liquidado por un titular en 30 días, por todas sus cuentas del "
              "núcleo, que llega a esto deja una alerta."),
    "nucleo_umbral_12_meses": Ajuste(
        tipo=DINERO, defecto=Decimal("300000.00"), minimo=Decimal("1000.00"), maximo=Decimal("100000000.00"),
        unidad="R$", etiqueta="Núcleo · acumulado en 12 meses",
        ayuda="Lo mismo, en doce meses."),
    "nucleo_fraccionamiento_horas": Ajuste(
        tipo=ENTERO, defecto=24, minimo=1, maximo=168,
        unidad="horas", etiqueta="Núcleo · ventana de fraccionamiento",
        ayuda="Tres o más operaciones por debajo del umbral, dentro de esta "
              "ventana, que juntas lo pasan: la forma clásica de esquivarlo."),
    "nucleo_velocidad_por_hora": Ajuste(
        tipo=ENTERO, defecto=10, minimo=1, maximo=1000,
        unidad="operaciones", etiqueta="Núcleo · operaciones por hora",
        ayuda="Más que esto en una hora, por titular, deja una alerta."),

    # ── La vía cripto: un solo número con tres estados ─────────────────────
    #
    # POR QUE UN NUMERO CON TRES ESTADOS Y NO DOS INTERRUPTORES
    #
    #   Lo natural sería dos: «acepta depósitos» y «acepta envíos». Pero dos
    #   interruptores permiten CUATRO combinaciones, y una de ellas —entrada
    #   abierta y salida cerrada— le atrapa la plata a quien deposite: entra y
    #   no puede salir. Con un solo número esa combinación no se puede
    #   configurar, ni siquiera por error de tipeo.
    #
    #   Es la misma regla que ya está escrita en `services/personal.py` sobre
    #   por qué no se vuelve personal a alguien con saldo: «atrapar la plata de
    #   alguien para cumplir una regla interna sería peor que la regla».
    #
    # POR QUE DE FABRICA VIENE EN 1 Y NO EN 0
    #
    #   Porque 0 cierra la salida, y el día del despliegue puede haber saldo de
    #   alguien adentro. En 1 no nace custodia nueva —que es lo que apura— y
    #   quien tenga saldo lo puede sacar. Pasar a 0 es un clic del panel
    #   DESPUES de comprobar que las cuentas 2.1.03 y 2.1.04 del libro mayor, y
    #   las órdenes de Bitcoin en «pagado» (no `btc_ves_wallets`), están en cero.
    #
    # LO QUE ESTE AJUSTE NO APAGA NUNCA, Y ES A PROPOSITO
    #
    #   Los webhooks que acreditan (`/api/credits/webhook`,
    #   `/api/crypto-send/webhook`, `/api/btc/webhook/blink`) siguen abiertos en
    #   los tres estados. Alguien puede haber pagado en la blockchain cinco
    #   minutos antes del apagado: esa plata ya salió de su billetera y no
    #   vuelve. Si el webhook estuviera cerrado, el pago existiría y el saldo
    #   no. No abre nada, porque la ruta que CREA el pago sí está cerrada: el
    #   webhook sólo puede terminar de acreditar lo que ya existía.
    #
    #   Las lecturas tampoco se cierran. La historia de lo ya operado tiene que
    #   seguir visible para conciliar y para el libro mayor; esconder la
    #   contabilidad no es apagar una vía, es perderla de vista.
    "cripto_abierta": Ajuste(
        tipo=ENTERO, defecto=1, minimo=0, maximo=2,
        unidad="0 = cerrada, 1 = sólo salida, 2 = abierta",
        etiqueta="Vía cripto (USDT, USDC y BTC Lightning)",
        ayuda="En 2 funciona como siempre. En 1 (fábrica) no entran depósitos "
              "nuevos y no nace saldo nuevo, pero quien ya tiene saldo lo puede "
              "sacar: es el estado para apagar sin atrapar la plata de nadie. "
              "En 0 no entra ni sale nada y las pantallas desaparecen; poné 0 "
              "recién cuando los saldos cripto estén en cero. Los avisos de "
              "pago siguen entrando en los tres estados, para no perder un "
              "depósito que ya se pagó."),
}
