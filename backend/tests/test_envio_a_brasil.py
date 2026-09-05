"""
tests/test_envio_a_brasil.py — Las reglas de la pantalla de enviar a Brasil.

POR QUE ESTAN ACA Y NO EN UN TEST DE JAVASCRIPT

    Este repositorio no tiene banco de pruebas de frontend. La lógica vive en
    `frontend/src/utils/envioABrasil.js` —fuera del JSX, para poder probarla— y
    se corre desde acá con node, igual que el resto de las reglas de pantalla
    que ya se prueban así.

QUE SOSTIENEN

    Tres cosas que estaban mal en la pantalla vieja, y ninguna era cosmética:

      1. El CPF no se validaba: sólo se miraba que el campo no estuviera
         vacío. Un CPF mal tipeado es plata que sale hacia una llave que no
         existe, y se entera alguien días después.
      2. El CPF y la llave PIX se mostraban enteros en la lista. Son datos de
         un tercero, en una pantalla que se abre en un teléfono.
      3. El mínimo, el máximo y el cupo se comprobaban DESPUES del PIN. El
         usuario ponía su PIN y ahí se enteraba de que el monto no iba.
"""
import json
import os
import pathlib
import subprocess

import pytest

_RAIZ = pathlib.Path(os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))
_MODULO = _RAIZ / "frontend" / "src" / "utils" / "envioABrasil.js"


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


# ══════════════════════════════════════════════════════════════════════════
# El CPF
# ══════════════════════════════════════════════════════════════════════════
#
# Los once dígitos traen DOS verificadores calculados a partir de los otros
# nueve. Un dígito cambiado o dos transpuestos —los dos errores que comete
# alguien copiando un número largo— no cierran la cuenta.

VALIDOS = ["529.982.247-25", "11144477735", "390.533.447-05", "529 982 247 25"]
INVALIDOS = [
    ("529.982.247-26", "un dígito cambiado"),
    ("529.982.274-25", "dos dígitos transpuestos"),
    ("111.111.111-11", "todos iguales: pasa el módulo 11 y no es de nadie"),
    ("000.000.000-00", "todos ceros"),
    ("1234567890", "diez dígitos"),
    ("529982247251", "doce dígitos"),
    ("", "vacío"),
    ("52998224725x", "una letra al final"),
]


def test_un_cpf_bien_formado_se_acepta():
    assert _js(f"{json.dumps(VALIDOS)}.map(m.cpfValido)") == [True] * len(VALIDOS)


def test_un_cpf_mal_tipeado_se_rechaza():
    resultados = _js(f"{json.dumps([v for v, _ in INVALIDOS])}.map(m.cpfValido)")
    fallos = [porque for (v, porque), ok in zip(INVALIDOS, resultados) if ok]
    assert not fallos, (
        "Estos CPF se aceptaron y no debían:\n  " + "\n  ".join(fallos)
        + "\n\nCada uno que pasa es un envío que puede salir hacia una llave "
          "que no existe.")


def test_la_letra_no_se_descarta_como_si_fuera_un_separador():
    """La indulgencia tiene un límite, y lo encontró una prueba.

    Los puntos, guiones y espacios se descartan: son cómo la gente escribe un
    CPF. Una letra no. `52998224725x` limpiaba a un CPF válido y se aceptaba.
    """
    assert _js("m.cpfValido('52998224725x')") is False
    assert _js("m.cpfValido('529.982.247-25')") is True


def test_el_cpf_se_muestra_con_su_formato_legal():
    assert _js("m.cpfLegible('52998224725')") == "529.982.247-25"
    assert _js("m.formatearCpf('5299822')") == "529.982.2"
    assert _js("m.formatearCpf('529982247259999')") == "529.982.247-25", (
        "El formateo tiene que cortar en once dígitos: si deja seguir, el "
        "campo acepta un número que después no valida y nadie entiende por qué.")


def test_el_cpf_no_se_publica_entero_en_la_lista():
    """En la lista va abreviado; entero, sólo en la pantalla de confirmar.

    Es el dato de un tercero en una pantalla que se abre en cualquier lado.
    Para reconocer a quién le mandás alcanzan las últimas cifras.
    """
    abreviado = _js("m.cpfAbreviado('529.982.247-25')")
    assert "529" not in abreviado and "982" not in abreviado, (
        f"El CPF abreviado ({abreviado}) todavía deja ver el principio.")
    assert abreviado.endswith("247-25"), (
        "Y tiene que dejar ver lo suficiente para reconocerlo.")


# ══════════════════════════════════════════════════════════════════════════
# La llave PIX
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("llave, tipo", [
    ("juan@correo.com", "correo"),
    ("11987654321", "telefono"),
    ("52998224725", "cpf"),
    ("9c2b1f30-1a2b-3c4d-5e6f-708192a3b4c5", "aleatoria"),
])
def test_se_reconoce_de_que_clase_es_la_llave(llave, tipo):
    """PIX admite cinco formas y cada una se abrevia distinta.

    Decir «Correo ju•••@gmail.com» en vez de «Llave ju•••» le dice al usuario
    qué está mirando sin mostrarle el dato entero.
    """
    assert _js(f"m.tipoDeLlave({json.dumps(llave)})") == tipo


def test_la_llave_tampoco_se_muestra_entera():
    correo = _js("m.llaveAbreviada('marcos.oliveira@example.com')")
    assert "marcos.oliveira" not in correo and correo.endswith("@example.com"), (
        f"El correo abreviado ({correo}) no oculta lo que tiene que ocultar, "
        "o esconde el dominio, que es lo que sirve para reconocerlo.")
    assert "1198765" not in _js("m.llaveAbreviada('11987654321')")


# ══════════════════════════════════════════════════════════════════════════
# El monto, comprobado ANTES del PIN
# ══════════════════════════════════════════════════════════════════════════

LIMITES = {"pix": {"min_brl": 10, "max_brl": 5000}}


def _validar(monto, saldo=10000, cupo=None):
    args = json.dumps({"monto": monto, "saldo": saldo,
                       "limites": LIMITES, "cupo": cupo})
    return _js(f"m.validarMonto({args})")


@pytest.mark.parametrize("monto, saldo, cupo, espera", [
    (5, 10000, None, "mínimo"),
    (9000, 10000, None, "máximo"),
    (500, 100, None, "saldo"),
    (500, 10000, {"aplica": True, "ops_restantes": 0}, "operaciones"),
    (500, 10000, {"aplica": True, "ops_restantes": 2, "ris_restantes": 300}, "cupo"),
])
def test_lo_que_el_servidor_va_a_rechazar_se_dice_antes(monto, saldo, cupo, espera):
    problema = _validar(monto, saldo, cupo)
    assert problema, (
        f"Un monto de {monto} tenía que dar problema por «{espera}» y pasó. "
        "Si la pantalla no lo dice, lo dice el servidor DESPUES del PIN: el "
        "usuario pone su PIN para nada.")
    assert espera in problema.lower(), (
        f"El aviso dice «{problema}», que no habla de «{espera}». Un mensaje "
        "que no nombra el problema real manda al usuario a arreglar otra cosa.")


def test_el_orden_de_los_avisos_manda_al_lugar_correcto():
    """Bajo el mínimo Y sin saldo: se dice el mínimo.

    «Saldo insuficiente» manda a recargar a alguien que en realidad tenía que
    escribir un número más grande.
    """
    assert "mínimo" in _validar(monto=5, saldo=1).lower()


def test_un_monto_que_va_no_da_problema():
    assert _validar(monto=200, saldo=10000,
                    cupo={"aplica": True, "ops_restantes": 2,
                          "ris_restantes": 300}) is None


def test_sin_limites_del_servidor_no_se_inventa_ninguno():
    """Si `/limits/me` no contestó, la pantalla deja pasar y decide el servidor.

    Es lo que hacía antes de todos modos. Lo que se perdería es avisar
    temprano, no la protección — y frenar por no haber podido leer los límites
    sería peor: cortaría envíos válidos por una consulta caída.
    """
    args = json.dumps({"monto": 5, "saldo": 10000, "limites": None, "cupo": None})
    assert _js(f"m.validarMonto({args})") is None


# ══════════════════════════════════════════════════════════════════════════
# La pantalla usa el sistema visual compartido
# ══════════════════════════════════════════════════════════════════════════

PANTALLA = _RAIZ / "frontend" / "src" / "pages" / "SendReais.jsx"


def test_la_pantalla_toma_los_valores_del_modulo_compartido():
    """Los tres flujos de envío se ven iguales porque usan el MISMO módulo.

    Con estilos copiados, esa igualdad dura hasta el primer retoque en una
    sola de las tres.
    """
    fuente = PANTALLA.read_text(encoding="utf-8")
    faltan = [i for i in ("from '../components/flujo'",
                          "from '../components/flujo/estilos'")
              if i not in fuente]
    assert not faltan, (
        "La pantalla de enviar a Brasil dejó de usar el sistema visual "
        "compartido: falta " + ", ".join(faltan))


def test_la_pantalla_no_escribe_colores_a_mano():
    import re
    visible = "\n".join(l for l in PANTALLA.read_text(encoding="utf-8").splitlines()
                        if not l.strip().startswith(("*", "//", "/*", "{/*")))
    sueltos = [c for c in re.findall(r"#[0-9a-fA-F]{6}\b", visible)]
    assert not sueltos, (
        f"Colores escritos a mano: {sueltos}. La paleta es `C`, en "
        "components/flujo/estilos.js.")


def test_el_monto_se_valida_antes_de_pedir_el_pin():
    """El orden es la garantía entera: comprobar después del PIN no sirve."""
    fuente = PANTALLA.read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("const pedirConfirmacion"):]
    cuerpo = cuerpo[:cuerpo.index("};")]
    assert cuerpo.index("problemaDelMonto") < cuerpo.index("setMostrarPin"), (
        "Se abre el PIN antes de mirar si el monto va. El usuario pone su PIN "
        "y recién después se entera de que el envío no salía.")
