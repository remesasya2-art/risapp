"""
Operación: lo que hace falta para operar el núcleo como infraestructura
financiera y no como laboratorio.

SEIS PIEZAS

    bitacora      quién hizo qué sobre el núcleo, con el antes y el después,
                  encadenada por hash como el libro. Un auditor puede probar
                  que no se tocó. Sólo se agrega.
    aprobaciones  el cuatro ojos general: las acciones sensibles se PIDEN y
                  otra persona las APRUEBA; recién ahí se ejecutan. Quien
                  pide no puede aprobar. Cubre cambiar la configuración del
                  núcleo mientras está prendido, transmitir un reporte y
                  comunicar un incidente al BCB.
    secretos      el puerto para leer credenciales y certificados por
                  nombre. Hoy, variables de entorno; mañana, un gestor de
                  secretos, sin que ningún adaptador cambie.
    salud         qué mira de verdad la salud del núcleo, y quién avisa
                  cuando algo se cae.
    registros     los registros del núcleo en JSON con campos fijos, y las
                  métricas que un tablero externo puede leer.
    respaldo      la exportación firmada de lo que la ley obliga a conservar,
                  y la comprobación de que un respaldo se puede leer.

LA FRONTERA SIGUE

    Nada de acá importa la aplicación salvo lo permitido (la configuración y
    la base de Mongo, para el interruptor). Lo que el núcleo necesita de la
    aplicación —avisar al personal, frenar un cambio de configuración— entra
    por registros de funciones que `server.py` llena al arrancar. Es el único
    puente, y es a propósito.
"""
