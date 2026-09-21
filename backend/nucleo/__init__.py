"""
nucleo — el núcleo de cuentas de la fintech que RIS quiere ser.

QUE ES

    Un núcleo de cuentas al estilo de una instituição de pagamento: cuentas de
    pago por titular, partida doble nativa (cada movimiento nace con sus dos
    asientos), libro inmutable con numeración correlativa y encadenado por
    hash, cierre diario, saldo derivado de los asientos.

    Vive en su propia base de datos, relacional (Postgres en producción,
    SQLite en los tests), con transacciones de verdad. La base actual de la
    aplicación (Mongo) sigue para todo lo demás.

POR QUE ESTA APAGADO

    Decisión del dueño del proyecto: la arquitectura se construye ahora y se
    prende el día que haya licencia. Hasta entonces:

      · De fábrica el núcleo está APAGADO: sus rutas contestan 404 a todo el
        mundo, también al super administrador. Nada en la interfaz.
      · En LABORATORIO, sólo el super administrador ve una pestaña «Núcleo»
        del panel, con datos de prueba. Los clientes no ven ni un botón, ni
        una ruta, ni una clave en `/limits`. Hay tests que lo sostienen.
      · ACTIVO queda reservado. Hoy se comporta igual que laboratorio, y un
        test lo dice: prenderlo de verdad es trabajo de otro día, con licencia.

LA FRONTERA

    Este paquete no importa nada de la aplicación salvo lo mínimo que hace
    falta para montar las rutas (la dependencia del super administrador y la
    lectura del modo desde la configuración). La aplicación no importa nada
    de acá salvo para registrar el router y anunciar el estado al arrancar.
    Un test recorre los imports y falla si la frontera se cruza.

    Motivo: el día que el núcleo se separe en su propio servicio —que es a
    donde va—, tiene que poder salir del repositorio sin arrastrar nada.

LOS EVENTOS Y LA COLA

    Cada asiento deja un evento en una bandeja de salida, en la misma
    transacción. Un trabajador los despacha como trabajos de una cola con
    turnos, reintentos con espera creciente y cola de muertos. Todo en la
    misma base que el libro, por la garantía que eso da: ver `cola.py`.
    El trabajador corre en el mismo proceso web mientras dure el
    laboratorio: ver `trabajador.py`.

LOS RIELES

    Por dónde entra y sale la plata de verdad: hoy el PIX, contra un
    simulador que habla como un liquidante (órdenes, avisos, DICT, códigos
    de rechazo del SPI, BR Code). El puerto está en `rieles/__init__.py`; el
    día del contrato se escribe el adaptador real con esa misma forma. Las
    operaciones, sus tres asientos y su línea de tiempo están en
    `rieles/operaciones.py`, y todo pasa por la cola.

EL DINERO VA EN CENTAVOS ENTEROS

    Los montos son enteros en la unidad mínima de la moneda (centavos para el
    real). Es lo que hacen los núcleos bancarios: un entero es exacto en toda
    base, en todo lenguaje y en todo formato, y una suma de enteros no
    redondea. En los bordes de la API viajan como texto («100.00»), igual que
    en el resto de la casa; adentro son `int`.
"""
