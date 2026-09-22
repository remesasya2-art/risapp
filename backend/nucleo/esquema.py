"""
El esquema del núcleo. Veintiuna tablas, y cada columna con su porqué.

    plan_de_cuentas   el plan contable (estilo COSIF, reducido). Cada cuenta
                      tiene naturaleza deudora o acreedora: es lo que decide
                      si un débito la sube o la baja.
    cuentas           las cuentas de pago de los titulares. Cada una cuelga
                      de una cuenta del plan (el pasivo «contas de pagamento»).
    asientos          el libro: uno por movimiento, con número correlativo,
                      hash del anterior y hash propio. NUNCA se edita ni se
                      borra: no hay función que lo haga.
    partidas          las líneas de cada asiento: debe o haber, en centavos.
                      La suma de debes es igual a la de haberes, siempre; lo
                      exige el código antes de escribir.
    cierres           un renglón por día cerrado: hasta qué asiento, con qué
                      hash, y los totales. Después del cierre no se asienta
                      con fecha de ese día ni anterior.
    eventos           la bandeja de salida: «pasó tal cosa», escrita en LA
                      MISMA transacción que la cosa. Un asiento y su evento
                      entran juntos o no entra ninguno. `publicado` en NULL
                      es «todavía nadie lo despachó».
    trabajos          la cola: lo que hay que hacer después, con turnos,
                      reintentos y cola de muertos. El porqué de cada
                      columna está en `nucleo/cola.py`.
    operaciones       cada cobro, pago o devolución por un riel (hoy, PIX):
                      su estado, su identificador punta a punta, su clave.
    operacion_estados la línea de tiempo de cada operación, sólo se agrega.
    avisos_riel       lo que el riel nos avisó, crudo, idempotente por su
                      identificador. Es la hoja para investigar.
    sim_claves        el directorio de claves del SIMULADOR (DICT de mentira),
                      con claves de prueba que se portan distinto.
    titulares         el legajo de cada persona: quién es, qué declaró, qué
                      riesgo tiene, si está aprobado y hasta cuándo. Una
                      cuenta de pago sólo se abre con un legajo aprobado.
    verificaciones    lo que el verificador contestó cada vez: puntajes,
                      situación del CPF, motivos. Nunca las fotos.
    cruces            cada cruce con una lista (sanciones, PEP) y cómo se
                      resolvió.
    sim_personas      las personas de prueba del simulador de identidad.
    sim_listas        las listas de prueba (CSNU, OFAC, PEP).
    alertas           lo que el monitoreo encontró: una por operación y regla.
    casos             el expediente: estado, analista, plazos, conclusión,
                      quién aprobó comunicar, acuse.
    caso_notas        lo que se fue anotando en el caso. Sólo se agrega.
    comunicaciones    cada comunicación al COAF (y cada no ocurrencia), con
                      el archivo que se mandó y el acuse que volvió.
    reportes          cada reporte regulatorio generado (balancete COSIF, CCS,
                      e-Financeira), con el archivo tal cual, su versión y el
                      protocolo de la transmisión. Sólo se agrega: una
                      corrección es una versión nueva, nunca una edición.

EL DINERO ES BIGINT EN CENTAVOS

    Ver el encabezado del paquete. Un `NUMERIC` sería exacto en Postgres y
    flotante en SQLite; el entero es exacto en las dos y no hay dos caminos.
"""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey,
    Index, Integer, MetaData, String, Table, Text, UniqueConstraint, func,
)

metadata = MetaData()

# Naturalezas contables. Deudora: el débito la aumenta (activo, egreso).
# Acreedora: el crédito la aumenta (pasivo, patrimonio, ingreso).
DEUDORA = "deudora"
ACREEDORA = "acreedora"

plan_de_cuentas = Table(
    "plan_de_cuentas", metadata,
    Column("codigo", String(20), primary_key=True),          # «2.1.01»
    Column("nombre", String(120), nullable=False),
    Column("grupo", String(20), nullable=False),              # activo, pasivo, patrimonio, ingreso, egreso
    Column("naturaleza", String(10), nullable=False),
    Column("de_titulares", Boolean, nullable=False, default=False),  # ¿cuelgan cuentas de pago de acá?
    CheckConstraint("naturaleza in ('deudora','acreedora')", name="naturaleza_valida"),
)

cuentas = Table(
    "cuentas", metadata,
    Column("id", String(40), primary_key=True),               # «cta_…»
    Column("titular_ref", String(80), nullable=False),        # referencia al titular en la app (user_id)
    Column("cuenta_contable", String(20), ForeignKey("plan_de_cuentas.codigo"), nullable=False),
    Column("moneda", String(3), nullable=False, default="BRL"),
    Column("estado", String(12), nullable=False, default="activa"),  # activa, bloqueada, cerrada
    Column("de_prueba", Boolean, nullable=False, default=True),      # todo lo del laboratorio es de prueba
    Column("creada", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # Cuándo se cerró. Hoy no hay función que cierre cuentas; la columna
    # existe porque el CCS informa el FIN de cada relación con su fecha, y
    # el día que alguien escriba el cierre tiene que anotarla acá.
    Column("cerrada_en", DateTime(timezone=True), nullable=True),
    CheckConstraint("estado in ('activa','bloqueada','cerrada')", name="estado_valido"),
    Index("ix_cuentas_titular", "titular_ref"),
)

asientos = Table(
    "asientos", metadata,
    Column("numero", BigInteger, primary_key=True, autoincrement=False),  # correlativo, lo asigna el libro
    Column("fecha", Date, nullable=False),                    # día contable
    Column("momento", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("descripcion", String(200), nullable=False),
    Column("referencia", String(120), nullable=False),        # idempotencia: una referencia, un asiento
    Column("comando", String(40), nullable=False),            # acreditar, debitar, transferir, tarifa, ajuste
    Column("actor", String(80), nullable=False),              # quién lo ordenó
    Column("hash_previo", String(64), nullable=False),
    Column("hash", String(64), nullable=False),
    UniqueConstraint("referencia", name="uq_asientos_referencia"),
    UniqueConstraint("hash", name="uq_asientos_hash"),
    Index("ix_asientos_fecha", "fecha"),
)

partidas = Table(
    "partidas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asiento", BigInteger, ForeignKey("asientos.numero"), nullable=False),
    Column("orden", Integer, nullable=False),                 # posición dentro del asiento
    Column("cuenta_contable", String(20), ForeignKey("plan_de_cuentas.codigo"), nullable=False),
    Column("cuenta", String(40), ForeignKey("cuentas.id"), nullable=True),  # sólo si es de un titular
    Column("debe", BigInteger, nullable=False, default=0),    # centavos
    Column("haber", BigInteger, nullable=False, default=0),   # centavos
    CheckConstraint("debe >= 0 and haber >= 0", name="montos_no_negativos"),
    CheckConstraint("(debe > 0) <> (haber > 0)", name="una_sola_columna"),
    Index("ix_partidas_cuenta", "cuenta"),
    Index("ix_partidas_asiento", "asiento"),
)

cierres = Table(
    "cierres", metadata,
    Column("dia", Date, primary_key=True),
    Column("hasta_asiento", BigInteger, nullable=False),      # el último asiento incluido (0 si no hubo)
    Column("hash_final", String(64), nullable=False),
    Column("asientos", Integer, nullable=False),
    Column("total_debe", BigInteger, nullable=False),
    Column("total_haber", BigInteger, nullable=False),
    Column("cerrado_en", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("cerrado_por", String(80), nullable=False),
    Column("nota", Text, nullable=True),
)

eventos = Table(
    "eventos", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tipo", String(60), nullable=False),               # «asiento_registrado», «dia_cerrado»
    Column("clave", String(120), nullable=False),             # sobre qué: «asiento:12», «cierre:2026-09-21»
    Column("carga", Text, nullable=False),                    # JSON canónico con lo que hace falta saber
    Column("creado", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("publicado", DateTime(timezone=True), nullable=True),  # NULL: pendiente de despachar
    # Un hecho, un evento. Es lo que hace inofensivo volver a anotarlo.
    UniqueConstraint("tipo", "clave", name="uq_eventos_tipo_clave"),
    Index("ix_eventos_publicado", "publicado"),
)

trabajos = Table(
    "trabajos", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tipo", String(60), nullable=False),               # el nombre del manejador (nucleo/tareas.py)
    Column("clave", String(120), nullable=False),             # idempotencia: (tipo, clave) es único
    Column("carga", Text, nullable=False),                    # JSON con lo que el manejador necesita
    Column("estado", String(12), nullable=False, default="pendiente"),
    Column("intentos", Integer, nullable=False, default=0),   # cuántas veces se tomó
    Column("max_intentos", Integer, nullable=False, default=6),
    Column("proximo_intento", DateTime(timezone=True), nullable=False),  # desde cuándo se puede tomar
    Column("tomado_por", String(80), nullable=True),          # el trabajador que lo tiene
    Column("tomado_hasta", DateTime(timezone=True), nullable=True),      # el turno; vencido, otro lo retoma
    Column("ultimo_error", Text, nullable=True),
    Column("resultado", Text, nullable=True),                 # lo que devolvió el manejador, si devolvió algo
    Column("origen_evento", Integer, ForeignKey("eventos.id"), nullable=True),  # si nació de un evento
    Column("creado", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("terminado", DateTime(timezone=True), nullable=True),
    UniqueConstraint("tipo", "clave", name="uq_trabajos_tipo_clave"),
    CheckConstraint("estado in ('pendiente','en_curso','hecho','muerto')", name="estado_del_trabajo_valido"),
    CheckConstraint("intentos >= 0 and max_intentos > 0", name="intentos_validos"),
    Index("ix_trabajos_para_tomar", "estado", "proximo_intento"),
)

operaciones = Table(
    "operaciones", metadata,
    Column("id", String(40), primary_key=True),               # «op_…»
    Column("riel", String(20), nullable=False),               # «simulador», mañana «liquidante»
    Column("direccion", String(12), nullable=False),          # entrada, salida, devolucion
    Column("estado", String(12), nullable=False),             # ver nucleo/rieles/operaciones.py
    Column("cuenta", String(40), ForeignKey("cuentas.id"), nullable=False),
    Column("monto", BigInteger, nullable=False),              # centavos
    Column("referencia", String(120), nullable=False),        # idempotencia del pedido
    Column("txid", String(35), nullable=True),                # el del cobro (BR Code)
    Column("end_to_end", String(32), nullable=True),          # el del SPI, cuando lo hay
    Column("clave", String(120), nullable=True),              # la clave PIX de la contraparte
    Column("contraparte", Text, nullable=True),               # JSON: nombre, ISPB, banco
    Column("descripcion", String(140), nullable=True),
    Column("motivo", String(200), nullable=True),             # del rechazo o de la devolución
    Column("origen", String(40), ForeignKey("operaciones.id"), nullable=True),  # la devolución apunta a su cobro
    Column("codigo_br", Text, nullable=True),                 # el BR Code del cobro
    Column("creada", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("actualizada", DateTime(timezone=True), nullable=True),
    UniqueConstraint("referencia", name="uq_operaciones_referencia"),
    UniqueConstraint("end_to_end", name="uq_operaciones_end_to_end"),
    CheckConstraint("direccion in ('entrada','salida','devolucion')", name="direccion_valida"),
    CheckConstraint("monto > 0", name="monto_positivo"),
    Index("ix_operaciones_cuenta", "cuenta"),
    Index("ix_operaciones_txid", "txid"),
)

operacion_estados = Table(
    "operacion_estados", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("operacion", String(40), ForeignKey("operaciones.id"), nullable=False),
    Column("estado", String(12), nullable=False),
    Column("detalle", String(300), nullable=True),
    Column("momento", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_operacion_estados_operacion", "operacion"),
)

avisos_riel = Table(
    "avisos_riel", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("riel", String(20), nullable=False),
    Column("id_externo", String(120), nullable=False),        # el del riel: un aviso, una fila
    Column("tipo", String(40), nullable=False),               # credito_recibido, estado_de_pago, devolucion_liquidada
    Column("carga", Text, nullable=False),                    # JSON, por lista de lo permitido
    Column("recibido", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("procesado", DateTime(timezone=True), nullable=True),
    Column("resultado", String(200), nullable=True),
    UniqueConstraint("riel", "id_externo", name="uq_avisos_riel_externo"),
)

sim_claves = Table(
    "sim_claves", metadata,
    Column("clave", String(120), primary_key=True),
    Column("tipo", String(10), nullable=False),               # cpf, cnpj, email, telefone, evp
    Column("nombre", String(120), nullable=False),
    Column("documento", String(20), nullable=False),          # CPF/CNPJ del titular, enmascarado al mostrar
    Column("ispb", String(8), nullable=False),
    Column("banco", String(80), nullable=False),
    Column("comportamiento", String(12), nullable=False, default="normal"),  # normal, rechaza, tarda
)

titulares = Table(
    "titulares", metadata,
    Column("id", String(40), primary_key=True),               # «tit_…»
    Column("documento", String(14), nullable=False),          # CPF o CNPJ, sólo dígitos
    Column("tipo", String(4), nullable=False),                # cpf, cnpj
    Column("nombre", String(120), nullable=False),
    Column("nacimiento", Date, nullable=True),
    Column("ocupacion", String(80), nullable=True),
    Column("renta_declarada", BigInteger, nullable=True),     # centavos por mes
    Column("pep_declarado", Boolean, nullable=False, default=False),   # lo que la persona dijo
    Column("pep", Boolean, nullable=False, default=False),             # lo que dijo o lo que la lista dijo
    Column("origen_de_fondos", String(30), nullable=True),
    Column("nivel_de_riesgo", String(8), nullable=True),      # bajo, medio, alto
    Column("estado", String(12), nullable=False, default="incompleto"),
    Column("vigente_hasta", Date, nullable=True),
    Column("motivo", String(300), nullable=True),             # del rechazo
    Column("decidido_por", String(80), nullable=True),
    Column("cruzado_en", DateTime(timezone=True), nullable=True),   # la última vez que se miró en las listas
    Column("creado", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("actualizado", DateTime(timezone=True), nullable=True),
    UniqueConstraint("documento", name="uq_titulares_documento"),
    CheckConstraint("estado in ('incompleto','en_revision','aprobado','rechazado','vencido')", name="estado_del_legajo_valido"),
)

verificaciones = Table(
    "verificaciones", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("titular", String(40), ForeignKey("titulares.id"), nullable=False),
    Column("proveedor", String(40), nullable=False),
    Column("puntaje_documento", Integer, nullable=False),
    Column("puntaje_vida", Integer, nullable=False),
    Column("puntaje_rostro", Integer, nullable=False),
    Column("situacion_cpf", String(20), nullable=False),
    Column("nombre_en_documento", String(120), nullable=False),
    Column("documento_vencido", Boolean, nullable=False, default=False),
    Column("aprobada", Boolean, nullable=False),
    Column("motivos", Text, nullable=True),                   # JSON, lista de textos
    Column("momento", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_verificaciones_titular", "titular"),
)

cruces = Table(
    "cruces", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("titular", String(40), ForeignKey("titulares.id"), nullable=False),
    Column("lista", String(20), nullable=False),              # CSNU, OFAC, PEP-CGU
    Column("clase", String(10), nullable=False),              # sanciones, pep
    Column("nombre_en_lista", String(120), nullable=False),
    Column("detalle", String(300), nullable=True),
    Column("momento", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("resuelto", Boolean, nullable=False, default=False),
    Column("resolucion", String(300), nullable=True),         # «falso positivo: …», «confirmado: …»
    Column("resuelto_por", String(80), nullable=True),
    Column("resuelto_en", DateTime(timezone=True), nullable=True),
    Index("ix_cruces_titular", "titular"),
)

sim_personas = Table(
    "sim_personas", metadata,
    Column("documento", String(14), primary_key=True),
    Column("nombre", String(120), nullable=False),
    Column("nacimiento", String(10), nullable=False),
    Column("comportamiento", String(20), nullable=False, default="normal"),
)

sim_listas = Table(
    "sim_listas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("lista", String(20), nullable=False),
    Column("documento", String(14), nullable=False),
    Column("nombre", String(120), nullable=False),
    Column("detalle", String(300), nullable=True),
    UniqueConstraint("lista", "documento", name="uq_sim_listas_lista_documento"),
)

alertas = Table(
    "alertas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("titular", String(40), nullable=False),            # el titular_ref de la cuenta (id del legajo)
    Column("cuenta", String(40), ForeignKey("cuentas.id"), nullable=False),
    Column("operacion", String(40), ForeignKey("operaciones.id"), nullable=False),
    Column("regla", String(30), nullable=False),
    Column("detalle", Text, nullable=True),                   # JSON con los números que la hicieron saltar
    Column("momento", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("caso", String(40), ForeignKey("casos.id"), nullable=True),
    UniqueConstraint("operacion", "regla", name="uq_alertas_operacion_regla"),
    Index("ix_alertas_titular", "titular"),
)

casos = Table(
    "casos", metadata,
    Column("id", String(40), primary_key=True),               # «caso_…»
    Column("titular", String(40), nullable=False),
    Column("origen", String(10), nullable=False),             # alerta, lista, manual
    Column("estado", String(12), nullable=False),             # abierto, en_analisis, concluido, comunicado, archivado
    Column("analista", String(80), nullable=True),
    Column("detalle", String(300), nullable=True),
    Column("abierto_en", DateTime(timezone=True), nullable=False),
    Column("analizar_hasta", DateTime(timezone=True), nullable=False),   # +45 días
    Column("concluido_en", DateTime(timezone=True), nullable=True),
    Column("conclusion", Text, nullable=True),
    Column("comunicar", Boolean, nullable=True),
    Column("comunicar_hasta", DateTime(timezone=True), nullable=True),   # +24 horas desde la conclusión
    Column("aprobado_por", String(80), nullable=True),        # la segunda firma
    Column("comunicado_en", DateTime(timezone=True), nullable=True),
    Column("acuse", String(60), nullable=True),
    Column("archivado_en", DateTime(timezone=True), nullable=True),
    CheckConstraint("estado in ('abierto','en_analisis','concluido','comunicado','archivado')", name="estado_del_caso_valido"),
    Index("ix_casos_titular", "titular"),
)

caso_notas = Table(
    "caso_notas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("caso", String(40), ForeignKey("casos.id"), nullable=False),
    Column("autor", String(80), nullable=False),
    Column("texto", Text, nullable=False),
    Column("momento", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_caso_notas_caso", "caso"),
)

comunicaciones = Table(
    "comunicaciones", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("caso", String(40), ForeignKey("casos.id"), nullable=True),   # NULL en una no ocurrencia
    Column("tipo", String(15), nullable=False),               # comunicacion, no_ocurrencia
    Column("periodo", Integer, nullable=True),                # el año, en una no ocurrencia
    Column("archivo", Text, nullable=False),                  # lo que se mandó, tal cual
    Column("acuse", String(60), nullable=False),
    Column("enviada_en", DateTime(timezone=True), nullable=False),
    Column("enviada_por", String(80), nullable=False),
    Column("aprobada_por", String(80), nullable=False),
    Column("comunicador", String(40), nullable=False),
)

reportes = Table(
    "reportes", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tipo", String(20), nullable=False),               # balancete, ccs, efinanceira
    Column("periodo", String(10), nullable=False),            # «2026-09», «2026-09-21», «2026-S2», «2026»
    Column("version", Integer, nullable=False, default=1),    # 1 es la primera; 2 en adelante, rectificaciones
    Column("documento", String(30), nullable=False),          # cómo lo llama el regulador: «CADOC 4010»
    Column("archivo", Text, nullable=False),                  # lo que se manda, tal cual
    Column("resumen", Text, nullable=False),                  # JSON con los números que la pestaña muestra
    Column("generado_en", DateTime(timezone=True), nullable=False),
    Column("generado_por", String(80), nullable=False),
    Column("transmitido_en", DateTime(timezone=True), nullable=True),
    Column("transmitido_por", String(80), nullable=True),
    Column("protocolo", String(60), nullable=True),           # lo que el sistema del BCB devolvió
    Column("transmisor", String(40), nullable=True),          # por qué puerto salió
    UniqueConstraint("tipo", "periodo", "version", name="uq_reportes_tipo_periodo_version"),
    Index("ix_reportes_tipo_periodo", "tipo", "periodo"),
)

# El hash del que no tiene anterior. Sesenta y cuatro ceros: se lee a simple
# vista como «el principio».
HASH_DEL_PRINCIPIO = "0" * 64
