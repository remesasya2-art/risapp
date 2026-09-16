"""
tests/test_nada_bloquea_el_hilo.py — Que nadie agarre el hilo y no lo suelte.

LA APLICACION CORRE EN UN SOLO HILO, Y ESO NO ES UN DESCUIDO

    `railway.toml` la arranca con `uvicorn server:app`, sin `--workers`, y el
    panel de Railway dice una réplica. Un proceso, un hilo. Funciona porque
    mientras espera algo de afuera —la base, una API— suelta el turno y atiende
    a otro.

    Todo depende de que NADIE SE QUEDE CON EL TURNO AGARRADO. Una llamada que
    no suelta no la paga sólo quien la pidió: la paga TODA la aplicación,
    incluido el que sólo está mirando su saldo.

LO QUE SE ENCONTRO, Y LO QUE COSTABA

    · El SDK de Mercado Pago es síncrono, y se lo llamaba directo en cuatro
      lugares. El peor: la pantalla de recarga pregunta CADA CINCO SEGUNDOS si
      el pago entró. A medio segundo la ida y vuelta —y el servidor está en
      Oregón mientras Mercado Pago está en Brasil—, DIEZ personas esperando su
      PIX a la vez consumían el segundo entero que el hilo tiene por segundo.
      Pasado eso la cola crece y no se recupera: Railway ve la aplicación
      colgada y la reinicia en plena hora pico.

    · `bcrypt` tarda 266 milisegundos medidos, a propósito. Cada inicio de
      sesión congelaba la aplicación ese cuarto de segundo. Y en el 2FA había
      dos casos de 2,7 segundos: generar los diez códigos de respaldo, y meter
      un código equivocado, que los prueba uno por uno contra los diez.

    · `pywebpush` es síncrono, y `avisar_al_personal` manda uno por persona del
      equipo. El reparto usa `asyncio.gather` para hacerlos a la vez, pero con
      una llamada bloqueante adentro el `gather` no sirve: se hacen en fila.

POR QUE HAY UNA GUARDA QUE LEE EL CODIGO

    Volver a escribir `verify_password(...)` en una ruta nueva es lo más fácil
    del mundo: es el nombre obvio y funciona perfecto en los tests. El daño no
    se ve hasta que hay carga, y ahí se ve como «la app está lenta», que no
    apunta a ningún lado. La guarda lo dice en el momento, con el nombre puesto.
"""
import ast
import asyncio
import os
import pathlib
import sys
import time

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _BACKEND)

from utils.security import (hash_password, hash_password_async,      # noqa: E402
                            verify_password, verify_password_async)


# ══════════════════════════════════════════════════════════════════════════
# 1. La propiedad de verdad: el hilo sigue latiendo
# ══════════════════════════════════════════════════════════════════════════
#
# Esto NO lee el código: lo corre y mide. Un test que sólo mira el texto se
# puede engañar; este no. Se cuenta cada cuánto late un reloj mientras se
# cifra: si algo agarra el hilo, aparece un salto del tamaño de la espera.

async def _el_salto_mas_grande(tarea, cada=0.005) -> float:
    """Corre `tarea` y devuelve el hueco más grande entre dos latidos.

    EL RELOJ ARRANCA ANTES QUE LA TAREA, Y NO ES UN DETALLE

        La primera versión de esto usaba `asyncio.gather(tarea, latir())` y
        SE DEJABA ENGAÑAR: `gather` arranca primero la tarea, así que el
        congelamiento pasaba ANTES del primer latido. Después el reloj latía
        cuarenta veces prolijas y el hueco más grande daba cinco milisegundos.
        Verde con el defecto puesto.

        Se descubrió rompiendo la guarda a propósito: la mutación la mató la
        otra guarda, la que lee el código, y ésta ni se inmutó. Por eso la
        primera marca se toma ANTES de largar nada, y el reloj late hasta que
        la tarea termina en vez de un número fijo de veces.
    """
    marcas = [time.perf_counter()]
    andando = True

    async def latir():
        while andando:
            await asyncio.sleep(cada)
            marcas.append(time.perf_counter())

    reloj = asyncio.create_task(latir())
    await asyncio.sleep(0)          # que el reloj tome la delantera
    try:
        await tarea
    finally:
        andando = False
        await reloj
    return max(b - a for a, b in zip(marcas, marcas[1:]))


def test_COMPROBAR_LA_CONTRASENA_NO_CONGELA_LA_APLICACION():
    """bcrypt tarda 266 ms medidos. Si eso pasa adentro del hilo, el reloj se
    queda quieto ese cuarto de segundo y con él todos los demás pedidos."""
    cifrada = hash_password("Clave.larga1!")
    salto = asyncio.run(
        _el_salto_mas_grande(verify_password_async("Clave.larga1!", cifrada)))
    assert salto < 0.10, f"el hilo se quedó quieto {salto*1000:.0f} ms"


def test_CIFRAR_LA_CONTRASENA_NO_CONGELA_LA_APLICACION():
    salto = asyncio.run(_el_salto_mas_grande(hash_password_async("Clave.larga1!")))
    assert salto < 0.10, f"el hilo se quedó quieto {salto*1000:.0f} ms"


def test_UNA_LLAMADA_LENTA_DE_AFUERA_NO_CONGELA_LA_APLICACION():
    """La forma que se usó para las cuatro llamadas a Mercado Pago, probada
    sobre algo que tarda de verdad. Es la propiedad que hay que sostener; qué
    función concreta la usa lo vigila la guarda de más abajo."""
    def tarda():
        time.sleep(0.3)
        return "listo"

    salto = asyncio.run(_el_salto_mas_grande(asyncio.to_thread(tarda)))
    assert salto < 0.10, f"el hilo se quedó quieto {salto*1000:.0f} ms"


def test_LAS_DOS_VERSIONES_DICEN_LO_MISMO():
    """Si la versión en otro hilo no contestara igual que la de siempre, esto
    no sería un cambio de rendimiento sino un agujero en el ingreso."""
    cifrada = asyncio.run(hash_password_async("Clave.larga1!"))
    assert verify_password("Clave.larga1!", cifrada) is True
    assert asyncio.run(verify_password_async("Clave.larga1!", cifrada)) is True
    assert asyncio.run(verify_password_async("otra", cifrada)) is False


def test_LOS_DIEZ_CODIGOS_DE_RESPALDO_SE_CIFRAN_A_LA_VEZ():
    """Uno por uno son diez veces 266 ms: 2,7 segundos de espera para quien
    está prendiendo su segundo factor. A la vez, tarda como uno solo."""
    from routes import security_2fa

    uno = time.perf_counter()
    hash_password("medida")
    uno = time.perf_counter() - uno

    arranque = time.perf_counter()
    plain, hashes = asyncio.run(security_2fa._generate_backup_codes())
    tardanza = time.perf_counter() - arranque

    assert len(plain) == len(hashes) == security_2fa.BACKUP_CODES_COUNT
    assert tardanza < uno * 4, (
        f"los {len(plain)} códigos tardaron {tardanza:.2f}s y uno solo tarda "
        f"{uno:.2f}s: se están cifrando en fila")


# ══════════════════════════════════════════════════════════════════════════
# 2. La guarda que recorre el código
# ══════════════════════════════════════════════════════════════════════════

# Lo que no puede llamarse DIRECTO desde una función `async`. Son síncronas:
# se quedan esperando y no sueltan el hilo.
POR_NOMBRE = {
    "hash_password": "usá hash_password_async",
    "verify_password": "usá verify_password_async",
    "webpush": "envolvelo en asyncio.to_thread",
}

# Los métodos del SDK de Mercado Pago, que es síncrono entero.
DEL_SDK_DE_PAGOS = {
    "get_payment_status": "asyncio.to_thread(mercadopago_service...)",
    "create_pix_payment": "asyncio.to_thread(mercadopago_service...)",
}


def _codigo_del_backend():
    for ruta in sorted(pathlib.Path(_BACKEND).rglob("*.py")):
        partes = ruta.parts
        if "tests" in partes or "__pycache__" in partes or "venv" in str(ruta):
            continue
        yield ruta


def _llamadas_bloqueantes_en_async(ruta: pathlib.Path):
    """Las llamadas que agarran el hilo, hechas desde una función `async`.

    Se mira la función que CONTIENE la llamada, y de las que la contienen, la
    más chica: un `async def` con un `def` adentro contiene a los dos, y lo que
    importa es el de más adentro. Adentro de una función normal estas llamadas
    están bien — el hilo aparte lo pone quien la llama.
    """
    try:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    except SyntaxError:                                   # pragma: no cover
        return
    funcs = [(n.lineno, n.end_lineno, n.name, isinstance(n, ast.AsyncFunctionDef))
             for n in ast.walk(arbol)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    for n in ast.walk(arbol):
        if not isinstance(n, ast.Call):
            continue
        que, consejo = None, ""
        if isinstance(n.func, ast.Name) and n.func.id in POR_NOMBRE:
            que, consejo = n.func.id, POR_NOMBRE[n.func.id]
        elif isinstance(n.func, ast.Attribute) and n.func.attr in DEL_SDK_DE_PAGOS:
            que, consejo = n.func.attr, DEL_SDK_DE_PAGOS[n.func.attr]
        if not que:
            continue
        dentro = sorted([f for f in funcs if f[0] <= n.lineno <= f[1]],
                        key=lambda f: f[1] - f[0])
        if dentro and dentro[0][3]:
            yield f"{ruta.name}:{n.lineno} {que}() en async {dentro[0][2]} — {consejo}"


def test_NADIE_LLAMA_A_BCRYPT_NI_AL_SDK_DE_PAGOS_DENTRO_DEL_HILO():
    """La guarda. Si alguien vuelve a escribir el nombre obvio, esto lo dice
    acá y no seis meses después, con carga, como «la app está lenta»."""
    encontrados = []
    for ruta in _codigo_del_backend():
        encontrados.extend(_llamadas_bloqueantes_en_async(ruta))
    assert not encontrados, "agarran el hilo y no lo sueltan:\n" + "\n".join(encontrados)


def test_LA_GUARDA_SABE_ENCONTRAR_LO_QUE_BUSCA(tmp_path):
    """La mutación de la guarda, escrita.

    Una guarda que recorre archivos y no encuentra nada da verde de las dos
    formas: porque está todo bien, o porque no está mirando. Acá se le da un
    archivo con el defecto puesto y se comprueba que lo vea — y uno con la
    forma correcta, para que no marque cualquier cosa.
    """
    malo = tmp_path / "malo.py"
    malo.write_text("async def entrar(c, h):\n    return verify_password(c, h)\n")
    assert list(_llamadas_bloqueantes_en_async(malo))

    bueno = tmp_path / "bueno.py"
    bueno.write_text("async def entrar(c, h):\n"
                     "    return await verify_password_async(c, h)\n")
    assert not list(_llamadas_bloqueantes_en_async(bueno))

    # Y adentro de una función normal está bien: el hilo lo pone quien llama.
    normal = tmp_path / "normal.py"
    normal.write_text("def entrar(c, h):\n    return verify_password(c, h)\n")
    assert not list(_llamadas_bloqueantes_en_async(normal))
