"""
tests/test_perfil.py — Las reglas de la pantalla «Mi Perfil».

POR QUE ESTAN ACA Y NO EN UN TEST DE JAVASCRIPT

    Este repositorio no tiene banco de pruebas de frontend. La lógica vive en
    `frontend/src/utils/perfil.js` —fuera del JSX, para poder probarla— y se
    corre desde acá con node, igual que las reglas de enviar a Venezuela y de
    enviar a Brasil.

QUE SOSTIENEN

    Cuatro cosas que estaban mal en la pantalla vieja, y ninguna era estética:

      1. La foto se leía de `user.picture`. El modelo del backend declara
         `profile_picture`: la rama de la foto no se ejecutaba nunca.
      2. Y cuando se ejecute, la URL sale de la base de datos. Tiene que pasar
         por la lista de lo permitido de `urlDeArchivo.js`, o es el mismo
         agujero que ese módulo vino a cerrar.
      3. La máscara del CPF movía un dígito real al final del tercer grupo:
         `***.***.**2-34` no tiene la forma de un CPF.
      4. La contraseña nueva podía ser idéntica a la vieja. El cambio decía que
         había salido bien y no cambiaba nada.
"""
import json
import os
import pathlib
import subprocess

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
_MODULO = _RAIZ / "frontend" / "src" / "utils" / "perfil.js"


def _js(cuerpo):
    """Corre una expresión contra el módulo real y devuelve su resultado."""
    if not _MODULO.exists():
        pytest.fail(f"No está {_MODULO.relative_to(_RAIZ)}. Si se movió, "
                    "actualizá este test; si se borró, sacalo.")
    guion = f"import * as m from '{_MODULO}';\nconsole.log(JSON.stringify({cuerpo}));"
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        pytest.fail(f"El módulo no corre:\n{r.stderr[-1500:]}")
    return json.loads(r.stdout.strip())


def _usuario(**campos):
    return json.dumps(campos)


# ══════════════════════════════════════════════════════════════════════════
# La foto
# ══════════════════════════════════════════════════════════════════════════

def test_la_foto_sale_del_campo_que_el_backend_declara():
    """`profile_picture`, no `picture`.

    Es el campo del modelo y el que lee el panel de administración. Mirar
    `picture` era mirar `undefined`: la rama de la foto no corría nunca.
    """
    assert _js(f"m.fotoDePerfil({_usuario(profile_picture='/api/media/f.png')})") \
        == '/api/media/f.png'
    assert _js(f"m.fotoDePerfil({_usuario(picture='/api/media/f.png')})") is None


def test_sin_foto_no_se_inventa_una_ruta():
    assert _js("m.fotoDePerfil({})") is None
    assert _js("m.fotoDePerfil(null)") is None


@pytest.mark.parametrize("valor, porque", [
    ("javascript:alert(1)", "el clásico"),
    ("java\tscript:alert(1)", "con un tabulador adentro del esquema"),
    (" javascript:alert(1)", "con un espacio delante"),
    ("//otro-sitio.com/f.png", "otro sitio, mismo protocolo"),
    ("data:image/svg+xml,<svg onload=alert(1)>", "un SVG lleva script adentro"),
])
def test_una_foto_que_no_es_una_foto_no_llega_al_src(valor, porque):
    """El valor sale de la base de datos, así que puede ser cualquier texto.

    Un `src` con `javascript:` no ejecuta nada por sí solo, pero este mismo
    campo lo abre el panel de administración con un `href`, y ahí sí. La regla
    es una sola para toda la aplicación: pasa por `rutaDeArchivo` o no se usa.
    """
    resultado = _js(f"m.fotoDePerfil({_usuario(profile_picture=valor)})")
    assert resultado is None, (
        f"Pasó una foto que no debía ({porque}): {resultado}")


# ══════════════════════════════════════════════════════════════════════════
# El CPF y el nombre
# ══════════════════════════════════════════════════════════════════════════

def test_el_cpf_se_tapa_con_la_forma_de_un_cpf():
    """`***.***.**2-34` movía un dígito real al final del tercer grupo.

    Se usa la misma regla que el flujo de Brasil: una sola forma de tapar un
    CPF en toda la aplicación.
    """
    tapado = _js(f"m.cpfDelPerfil({_usuario(cpf_number='529.982.247-25')})")
    assert "529" not in tapado and "982" not in tapado, (
        f"El CPF tapado ({tapado}) todavía deja ver el principio.")
    assert tapado.endswith("247-25"), (
        "Y tiene que dejar ver lo suficiente para reconocerlo como propio.")


def test_sin_cpf_la_fila_no_se_dibuja():
    assert _js("m.cpfDelPerfil({})") is None


def test_el_nombre_cae_al_de_la_cuenta_y_despues_a_un_texto():
    assert _js(f"m.nombreVisible({_usuario(full_name='Ana Gómez', name='ana')})") == 'Ana Gómez'
    assert _js(f"m.nombreVisible({_usuario(name='ana')})") == 'ana'
    assert _js("m.nombreVisible({})") == 'Sin nombre'


# ══════════════════════════════════════════════════════════════════════════
# La verificación
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("estado, clave", [
    ("verified", "verificado"),
    ("pending", "pendiente"),
    ("rejected", "rechazado"),
    ("unverified", "sin_verificar"),
    (None, "sin_verificar"),
])
def test_cada_estado_del_kyc_tiene_su_lectura(estado, clave):
    assert _js(f"m.estadoDeVerificacion({json.dumps(estado)}).clave") == clave


def test_al_rechazado_se_le_vuelve_a_ofrecer_verificar():
    """Rechazado no es final: casi siempre es una foto que salió movida."""
    assert _js(f"m.convieneVerificar({_usuario(verification_status='rejected')})") is True
    assert _js(f"m.convieneVerificar({_usuario(verification_status='verified')})") is False


# ══════════════════════════════════════════════════════════════════════════
# El cambio de contraseña
# ══════════════════════════════════════════════════════════════════════════

BUENA = "Contra$eña9"


def _cambio(actual, nueva, repetida):
    args = json.dumps({"actual": actual, "nueva": nueva, "repetida": repetida})
    return _js(f"m.problemaDelCambioDeClave({args})")


def test_la_contrasena_nueva_no_puede_ser_la_misma_que_la_vieja():
    """Ni la pantalla ni el servidor lo miraban.

    El cambio salía «bien» y no cambiaba nada. Quien cambia su contraseña es
    alguien que sospecha que le entraron a la cuenta: un cartel verde por no
    haber hecho nada es peor que no dejarlo hacerlo.
    """
    problema = _cambio(BUENA, BUENA, BUENA)
    assert problema and "distinta" in problema.lower(), (
        f"Se aceptó cambiar la contraseña por la misma (dijo: {problema!r}).")


@pytest.mark.parametrize("actual, nueva, repetida, espera", [
    ("", BUENA, BUENA, "actual"),
    (BUENA, "", "", "nueva"),
    ("Vieja$1abc", "corta", "corta", "8 caracteres"),
    ("Vieja$1abc", BUENA, "Otra$Cosa9", "coinciden"),
])
def test_lo_que_va_a_fallar_se_dice_antes_de_llamar(actual, nueva, repetida, espera):
    problema = _cambio(actual, nueva, repetida)
    assert problema, f"Tenía que dar problema por «{espera}» y pasó."
    assert espera in problema.lower(), (
        f"El aviso dice «{problema}», que no habla de «{espera}». Un mensaje "
        "que no nombra el problema real manda a arreglar otra cosa.")


def test_el_orden_manda_al_lugar_correcto():
    """Contraseña floja Y repetición distinta: se dice lo de la política.

    «No coinciden» manda a corregir la repetición de una contraseña que igual
    iba a ser rechazada. Es el mismo criterio que en los flujos de envío.
    """
    problema = _cambio("Vieja$1abc", "corta", "otra")
    assert "coinciden" not in problema.lower()


def test_un_cambio_que_va_no_da_problema():
    assert _cambio("Vieja$1abc", BUENA, BUENA) is None


# ══════════════════════════════════════════════════════════════════════════
# Las notificaciones
# ══════════════════════════════════════════════════════════════════════════

def test_el_permiso_denegado_se_explica_y_dice_donde_se_arregla():
    """Era el caso más común y el único que no se contemplaba.

    Con el permiso denegado el interruptor se veía apagado y clickearlo no
    hacía nada visible: el navegador no vuelve a preguntar. El usuario
    clickeaba sin entender.
    """
    info = json.dumps({"serviceWorker": True, "pushManager": True,
                       "notification": True, "isIOS": False, "isPWA": False,
                       "permission": "denied"})
    aviso = _js(f"m.motivoSinNotificaciones({info})")
    assert aviso and "barra de direcciones" in aviso.lower(), (
        f"El aviso ({aviso}) no dice dónde se arregla.")


def test_en_iphone_sin_instalar_se_dice_como_instalar():
    info = json.dumps({"serviceWorker": True, "pushManager": False,
                       "notification": False, "isIOS": True, "isPWA": False,
                       "permission": "default"})
    aviso = _js(f"m.motivoSinNotificaciones({info})")
    assert "inicio" in aviso.lower()


def test_cuando_se_puede_no_se_muestra_ningun_aviso():
    info = json.dumps({"serviceWorker": True, "pushManager": True,
                       "notification": True, "isIOS": False, "isPWA": False,
                       "permission": "default"})
    assert _js(f"m.motivoSinNotificaciones({info})") is None


# ══════════════════════════════════════════════════════════════════════════
# El panel del rol
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rol, destino", [
    ("socio", "/partner"),
    ("socio_gestor", "/gestor"),
    ("admin", "/admin"),
    ("super_admin", "/admin"),
])
def test_cada_rol_lleva_a_su_panel(rol, destino):
    assert _js(f"m.panelDelRol({json.dumps(rol)}).destino") == destino


def test_un_usuario_comun_no_ve_ningun_panel():
    assert _js("m.panelDelRol('user')") is None
    assert _js("m.panelDelRol(undefined)") is None


# ══════════════════════════════════════════════════════════════════════════
# La pantalla usa el sistema visual compartido
# ══════════════════════════════════════════════════════════════════════════

PANTALLAS = [
    _RAIZ / "frontend" / "src" / "pages" / "Profile.jsx",
    _RAIZ / "frontend" / "src" / "components" / "PinSettings.jsx",
    _RAIZ / "frontend" / "src" / "components" / "WebAuthnSettings.jsx",
]


@pytest.mark.parametrize("pantalla", PANTALLAS, ids=lambda p: p.name)
def test_la_pantalla_toma_los_valores_del_modulo_compartido(pantalla):
    """El perfil se ve igual que los tres flujos porque usa el MISMO módulo.

    Con estilos copiados, esa igualdad dura hasta el primer retoque en uno solo
    de los cuatro.
    """
    fuente = pantalla.read_text(encoding="utf-8")
    assert "flujo/estilos" in fuente, (
        f"{pantalla.name} dejó de usar el sistema visual compartido.")


@pytest.mark.parametrize("pantalla", PANTALLAS, ids=lambda p: p.name)
def test_la_pantalla_no_escribe_colores_a_mano(pantalla):
    import re
    visible = "\n".join(l for l in pantalla.read_text(encoding="utf-8").splitlines()
                        if not l.strip().startswith(("*", "//", "/*", "{/*")))
    sueltos = re.findall(r"#[0-9a-fA-F]{6}\b", visible)
    # `#fff` sobre el fondo oscuro del panel del rol es el único literal que
    # queda, y tiene tres dígitos: no cae acá. Cualquier color de seis sí.
    assert not sueltos, (
        f"Colores escritos a mano en {pantalla.name}: {sueltos}. La paleta es "
        "`C`, en components/flujo/estilos.js.")


def test_no_se_manda_una_selfie_que_el_endpoint_no_recibe():
    """`ChangePasswordRequest` tiene tres campos y ninguno es una imagen.

    La pantalla mandaba `selfie_image: 'data:image/png;base64,placeholder'`.
    Pydantic lo descartaba, así que no rompía nada — pero el próximo que lea
    esa línea va a salir a buscar la cámara que nunca hubo.
    """
    fuente = PANTALLAS[0].read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("const cambiarClave"):]
    cuerpo = cuerpo[:cuerpo.index("const regenerarRespaldos")]
    assert "selfie" not in cuerpo.lower()


@pytest.mark.parametrize("cuadro", ["window.prompt", "window.confirm"])
def test_nada_se_pregunta_con_un_cuadro_nativo(cuadro):
    """Los dos fallan callados, y uno además deja la contraseña a la vista.

    `window.prompt` no enmascara lo que se escribe: la contraseña de la cuenta
    quedaba a la vista de cualquiera que mirara la pantalla. Y los dos cuadros
    se pueden bloquear —pasa en la aplicación instalada—: `prompt` devuelve
    null y `confirm` devuelve false, así que el botón no hace absolutamente
    nada, sin error. Un botón que a veces no hace nada es peor que uno que
    falla.
    """
    for pantalla in PANTALLAS:
        visible = "\n".join(l for l in pantalla.read_text(encoding="utf-8").splitlines()
                            if not l.strip().startswith(("*", "//", "/*")))
        assert cuadro not in visible, (
            f"{pantalla.name} volvió a preguntar con {cuadro}.")


def test_el_boton_apagado_dice_por_que_esta_apagado():
    """Guardar está deshabilitado mientras la contraseña no va.

    La lista en vivo cubre la política y el «no coincide» tiene su línea, pero
    «tiene que ser distinta de la actual» no se veía en ningún lado: el botón
    quedaba gris y nada explicaba por qué. Un botón apagado sin motivo a la
    vista es una pared.
    """
    fuente = PANTALLAS[0].read_text(encoding="utf-8")
    assert "empezoAEscribir && problemaDeLaClave" in fuente, (
        "El modal ya no muestra el motivo por el que Guardar está apagado.")
