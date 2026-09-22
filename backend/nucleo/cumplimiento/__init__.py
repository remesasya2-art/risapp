"""
Cumplimiento: lo que se registra porque el regulador lo va a pedir, y el
calendario que dice qué vence cuándo.

CUATRO PIEZAS

    dias_habiles  los plazos de la ouvidoria y del CCS se cuentan en días
                  hábiles de Brasil: sin sábados, domingos ni feriados
                  nacionales. Está acá para que nadie los cuente a mano.
    incidentes    el registro de incidentes operativos y de seguridad
                  (Resolución BCB 85/2021): qué pasó, desde y hasta cuándo,
                  a cuántos clientes tocó, la causa, las acciones. Uno
                  relevante se comunica al Banco Central, con plazo; y una
                  vez al año va el informe.
    ouvidoria     los reclamos que llegan a la ouvidoria (Resolución CMN
                  4.860/2020): protocolo propio, diez días hábiles para
                  responder, respuesta y resultado. Cita el caso de la mesa
                  de ayuda cuando viene de ahí. Una vez por semestre, el
                  informe.
    calendario    qué obligación vence cuándo, y en qué está: pendiente,
                  generada, transmitida. No se guarda: se deduce de las
                  tablas cada vez que se mira, así nunca está desactualizado.

LO QUE SE CONSERVA

    Incidentes y reclamos se conservan cinco años como mínimo (las dos
    resoluciones lo piden). No hay función que borre ni edite: lo que
    cambia con el tiempo (la causa, la respuesta) se escribe una sola vez
    al cerrar, y lo demás son notas que sólo se agregan.
"""
