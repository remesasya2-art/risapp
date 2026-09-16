"""
services/perfil.py — Lo que una persona puede ver de su propia cuenta.

POR QUE ESTO ESTA EN UN SOLO LUGAR

    Hay CINCO sitios que le mandan al navegador el documento del usuario, y los
    cinco alimentan exactamente el mismo objeto del frontend: `setUser()` en
    `AuthContext`.

        GET  /auth/me                     al abrir la aplicación
        POST /auth/login-password         la puerta principal
        POST /auth/2fa/verify             la puerta con segundo factor
        POST /auth/2fa/enroll-confirm     la puerta del alta del segundo factor
        POST /webauthn/login/verify       la puerta de la huella

    Cada uno tenía su propia lista de lo PROHIBIDO, escrita a mano, y las cinco
    habían quedado distintas. Medido corriendo las rutas, con un usuario que
    tuviera puestos los campos que la aplicación escribe de verdad:

        /auth/me                 filtraba 18 campos que no son suyos
        /auth/login-password     filtraba 15
        /webauthn/login/verify   filtraba menos, porque su lista tenía cuatro
                                 nombres más — entre ellos `pin_hash`, que las
                                 otras dejaban salir

    Esa última línea es el argumento entero. Alguien se acordó de `pin_hash` en
    UNA de las cinco listas. Con listas separadas, acordarse en una no protege
    las otras cuatro, y nadie se entera.

QUE SALIA

    La semilla del segundo factor y la que está a medio activar, los códigos de
    respaldo, el hash del PIN y sus intentos fallidos, las credenciales de la
    huella y sus retos, la suscripción de avisos con su secreto, el token de
    notificaciones, el correo de una cuenta borrada, los permisos internos, el
    legajo laboral, el motivo de un baneo, el motivo de rechazo del KYC, el
    enlace al Drive con sus documentos y quién borró la cuenta.

    La peor es la semilla: NO VENCE. Quien la tenga genera códigos válidos para
    siempre. Una sesión robada se revoca; una semilla filtrada obliga a darse de
    alta de nuevo. Y no hace falta un atacante remoto: cualquier XSS, o una
    extensión del navegador —ya vimos extensiones inyectando scripts acá— pasa
    de robar una sesión a quedarse con el segundo factor.

POR QUE LISTA DE LO PERMITIDO

    Es la regla del proyecto, y éste es el caso que la motiva. Una lista de lo
    prohibido deja pasar cada campo nuevo hasta que alguien se acuerde, y nadie
    se acordó de `two_factor_secret` el día que se agregó el segundo factor.

    Tiene un precio, y es el modo de fallar silencioso: un campo que nadie
    agregue acá no sale, la ruta contesta 200 igual, y la pantalla muestra un
    hueco. Por eso `tests/test_lo_que_ve_su_dueno.py` prueba las dos mitades.

DE DONDE SALE CADA NOMBRE

    De lo que el frontend lee de verdad: se recorrieron los archivos que usan
    `useAuth()`. Los de KYC que aparecían en esa búsqueda —`selfie_image`,
    `cpf_image`, `id_document_image`, `document_number`— NO están, y no pueden
    estar: se comprobó que NO VIVEN en `users` sino en `verifications`, y que
    a la pantalla llegan por `userHistory.user`, que es otra ruta y sólo la ve
    un administrador.
"""
from services import saldos
from services.money import from_db, to_float

# TODOS LOS SALDOS, EN UN SOLO LUGAR, Y LAS CUENTAS RIS NO SE ESCRIBEN: SE PIDEN.
#
# Con lista de lo prohibido el documento salía entero y un bucle convertía todo
# lo que empezara con `balance_`: un saldo nuevo se mostraba solo. Con lista de
# lo permitido eso ya no alcanza, así que los saldos están juntos y con nombre
# propio —en vez de sueltos entre los demás campos— para que el que agregue el
# próximo tenga que ver esta lista.
#
# `services/saldos.py` ya las declara, y una de ellas es la del bono de
# bienvenida. Hay una guarda —`test_solo_el_envio_a_venezuela_sabe_gastar_el
# _bono`— que exige que la lista de archivos que NOMBRAN esa cuenta se
# mantenga corta, porque de eso depende la regla «el bono se gasta sólo en
# envíos a Venezuela». Escribirla acá a mano habría agregado un archivo más a
# esa lista para no ganar nada: este módulo sólo la muestra, no la mueve.
#
# De paso queda imposible que las dos listas discrepen: una cuenta RIS nueva
# aparece acá sola.
LOS_SALDOS = tuple(sorted(saldos.CUENTAS)) + (
    "balance_ves", "balance_usdt", "balance_usdc",
    # Nombres viejos. Una cuenta de hace tiempo puede tener la plata guardada
    # con el nombre anterior —`scripts/verificar_saldo_de_terceros.py` existe
    # justamente para buscarlas— y la ruta de login los convierte igual. Sin
    # ellos acá, esa plata dejaría de verse sin que nadie lo notara.
    "balance_terceros", "balance_personal",
)

LO_QUE_VE_SU_DUENO = {
    "_id": 0,

    # Quién es
    "user_id": 1, "email": 1, "name": 1, "phone": 1, "phone_number": 1,
    "role": 1, "status": 1, "profile_picture": 1, "picture": 1,

    # Estado de la cuenta. `must_change_password` lo lee `AuthContext` para
    # mandar a la pantalla de cambio obligado: sin él, esa pantalla no aparece
    # nunca y alguien se queda con una contraseña temporal para siempre.
    "verification_status": 1, "email_verified": 1, "password_set": 1,
    "must_change_password": 1,

    # Plata
    **{campo: 1 for campo in LOS_SALDOS},
    "bono": 1,

    # Lo suyo: su CPF, su código para invitar, sus códigos de rol.
    "cpf_number": 1, "referral_code": 1, "gestor_code": 1, "partner_code": 1,
    "is_partner": 1,

    # De dónde despacha, y desde cuándo está.
    "cep_origen": 1, "created_at": 1, "last_login": 1,
}

# Los nombres permitidos, sin el `_id: 0` que es de la proyección de Mongo.
LO_PERMITIDO = frozenset(c for c, v in LO_QUE_VE_SU_DUENO.items() if v == 1)


# ══════════════════════════════════════════════════════════════════════════
# LO QUE EL PANEL VE DE UN USUARIO
# ══════════════════════════════════════════════════════════════════════════
#
# QUE PASABA
#
#     `/api/admin/users` devolvía CADA usuario con la proyección
#     `{"_id": 0, "password_hash": 0}` — otra lista de lo prohibido— o sea el
#     documento entero menos la contraseña. Comprobado corriendo la ruta con un
#     `agent`, que es el rol más bajo con acceso al panel:
#
#         jefe@ejemplo.com   rol=super_admin   two_factor_secret, pin_hash,
#                                              webauthn_credentials
#         ana@ejemplo.com    rol=user          pin_hash, push_token,
#                                              web_push_subscription
#
#     Y no hacía falta saber ningún identificador: venían todos en una sola
#     respuesta.
#
# POR QUE ES PEOR QUE LA FUGA DE `/auth/me`
#
#     Ahí cada persona veía cosas SUYAS. Acá se ve la semilla del segundo factor
#     de OTRO, y la del dueño de la empresa entre ellas. Quien la tenga genera
#     los códigos del jefe para siempre: es la diferencia entre ver de más y
#     poder entrar como otro.
#
#     El hash del PIN es el mismo problema en chico. Son cuatro dígitos: diez
#     mil combinaciones. Contra un hash que ya se tiene en la mano, eso no es
#     una barrera, es un rato.
#
#     La ruta pide el permiso `users.view`, que es el de atención al cliente.
#     No es un permiso de administración de seguridad: es el que se le da a
#     quien atiende. Ese permiso tiene que servir para ver a un cliente, no para
#     quedarse con su llave.
#
# POR QUE ESTA LISTA ES MAS ANCHA QUE LA DEL DUEÑO
#
#     Porque el trabajo es otro. Quien atiende necesita ver el estado del KYC,
#     los saldos, el rol y las fechas de alguien que no es él. Lo que no
#     necesita —ni debería poder— es su forma de entrar.
#
#     Los nombres salieron de recorrer `AdminPanel.jsx`, que es el único
#     consumidor de estas rutas en todo el frontend.
#
#     Las fotos del KYC no están y no hacen falta: no viven en `users` sino en
#     `verifications`, y la ruta `/complete` las agrega DESPUES de esta
#     proyección, sacándolas del cofre.
LO_QUE_VE_EL_PANEL = {
    "_id": 0,

    # Quién es
    "user_id": 1, "name": 1, "email": 1, "phone": 1, "phone_number": 1,
    "profile_picture": 1, "picture": 1,

    # Para atenderlo: en qué estado está su cuenta y su verificación
    "role": 1, "status": 1, "verification_status": 1, "email_verified": 1,
    "password_set": 1,

    # Su plata, que es de lo que más se pregunta
    **{campo: 1 for campo in LOS_SALDOS},

    # Sus códigos y su CPF
    "cpf_number": 1, "referral_code": 1, "gestor_code": 1, "partner_code": 1,
    "is_partner": 1, "is_agent": 1,

    # Desde cuándo está y cuándo entró por última vez
    "cep_origen": 1, "created_at": 1, "last_login": 1,
}

LO_PERMITIDO_AL_PANEL = frozenset(
    c for c, v in LO_QUE_VE_EL_PANEL.items() if v == 1)


def para_su_dueno(documento: dict | None) -> dict | None:
    """Deja el documento del usuario listo para mandárselo a su dueño.

    Recorta por la lista de lo permitido, convierte los saldos a número y
    reemplaza el bono crudo por el bono interpretado.

    Lo usan las cuatro puertas de entrada, que leen el documento entero porque
    necesitan la contraseña o la semilla para dejar pasar. `/auth/me` no la
    llama: proyecta desde Mongo con la misma lista, que es mejor todavía —lo
    que no sale de la base no se puede filtrar por descuido más adelante.
    """
    if not documento:
        return documento
    recortado = {c: v for c, v in documento.items() if c in LO_PERMITIDO}
    recortado["password_set"] = recortado.get("password_set", False)
    return terminar_de_armar(recortado)


def terminar_de_armar(usuario: dict) -> dict:
    """Los saldos a número y el bono interpretado. Modifica y devuelve.

    SE RECORREN LOS SALDOS POR PREFIJO, no por una lista escrita a mano. Una
    lista de campos a CONVERTIR no es lo mismo que una lista de campos a
    EXPONER: acá no se decide qué se muestra, sino de qué tipo sale. Olvidarse
    de un nombre no filtra nada — devuelve 500, porque un `Decimal128` no se
    convierte a JSON. Ya pasó: a la lista del login le faltaba la cuenta del
    bono de bienvenida, y toda cuenta registrada desde que ese bono existe
    quedó sin poder entrar.

    (Acá no se la nombra a propósito: hay una guarda que exige que la lista de
    archivos que nombran esa cuenta se mantenga corta, y este módulo sólo la
    muestra.)
    """
    for f in [k for k in usuario if k.startswith("balance_")]:
        if usuario[f] is not None:
            usuario[f] = to_float(from_db(usuario[f]))
    # El bono, ya interpretado: cuánto hay, si está bloqueado y el texto que lo
    # explica. Reemplaza al subdocumento crudo por dos motivos: la pantalla no
    # tiene que deducir la regla —el texto lo arma el servidor, así que el monto
    # y la condición no pueden discrepar— y deja de viajar al navegador el id de
    # quien refirió, que es el identificador de OTRA persona.
    if "bono" in usuario:
        from services import bonos
        usuario["bono"] = bonos.para_la_pantalla(usuario)
    return usuario
