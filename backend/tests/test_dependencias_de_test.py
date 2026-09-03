"""
tests/test_dependencias_de_test.py — Que la suite no pueda mentir por omisión.

POR QUE ESTE ARCHIVO EXISTE

    Veintiún archivos de este directorio empiezan con

        pytest.importorskip("mongomock_motor")

    que es lo correcto: sin la base de mentira esos tests no pueden correr, y
    saltarlos es mejor que reventar. El problema es lo que pasa cuando la
    librería falta de verdad: 551 tests desaparecen —los del saldo, el libro,
    las recargas, el motor contable— y pytest termina en VERDE. Una suite que
    da verde sin haber probado la plata es peor que no tener suite, porque
    alguien confía en ella.

    Este archivo es el único que NO se salta. Si las dependencias de test no
    están, la suite se pone roja y dice cuál falta.

    Medido en este repo: 1782 pasan con mongomock-motor; 1231 pasan y 120 se
    saltan sin ella. Cero fallos en los dos casos.
"""
import importlib

import pytest

# Nombre de import → cómo se instala.
NECESARIAS = {
    "mongomock_motor": "mongomock-motor",
    "mongomock": "mongomock",
}


@pytest.mark.parametrize("modulo, paquete", sorted(NECESARIAS.items()))
def test_la_dependencia_de_test_esta_instalada(modulo, paquete):
    try:
        importlib.import_module(modulo)
    except ImportError as e:
        pytest.fail(
            f"Falta `{paquete}`. Sin ella los tests que la usan se SALTAN en "
            f"silencio y la suite da verde sin haber probado nada de lo que "
            f"mueve plata.\n\n"
            f"    pip install -r requirements-dev.txt\n\n"
            f"(import de `{modulo}` falló con: {e})"
        )
