"""
tests/test_la_guia_de_replicas.py — Los comandos de arranque de
docs/mongo-con-replicas.md esperan a que el nombre del contenedor sea suyo
antes de arrancar Mongo como conjunto de réplicas.

El 25 de septiembre de 2026 Mongo se reinició en Railway mientras su nombre en
la red privada todavía apuntaba al contenedor viejo: no se encontró en su
propia lista de miembros y quedó sin primario, sin aceptar escrituras, hasta
que se volvió atrás a mano. El comando no esperaba. Estos comandos se pegan en
el panel de Railway y no los corre ningún test; esto vigila que la espera no
se pierda en una edición de la guía.

El ensayo de la espera, con MongoDB 8 y nombres que tardan en apuntar, está
contado en la sección 7 de la guía.
"""
import os
import re

GUIA = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "mongo-con-replicas.md")
ARRANQUE_EN_REPLICAS = "exec docker-entrypoint.sh mongod --replSet"


def _comandos():
    with open(GUIA, encoding="utf-8") as f:
        texto = f.read()
    return [linea.strip() for linea in texto.split("\n")
            if linea.strip().startswith("bash -c '") and ARRANQUE_EN_REPLICAS in linea]


def test_LA_GUIA_TIENE_EL_COMANDO_DEL_PRIMERO_Y_EL_DE_LOS_NUEVOS():
    comandos = _comandos()
    assert len(comandos) == 2, f"se esperaban 2 comandos que arrancan en réplicas, hay {len(comandos)}"
    assert any("rs.initiate" in c for c in comandos), "falta el del primer miembro (sección 1)"
    assert any("rs.add" in c for c in comandos), "falta el de los miembros nuevos (sección 9)"


def test_CADA_COMANDO_ESPERA_A_SU_NOMBRE_ANTES_DE_ARRANCAR():
    for c in _comandos():
        arranque = c.index(ARRANQUE_EN_REPLICAS)
        espera = c.find("grep -q \"ES ESTE\"")
        assert 0 <= espera < arranque, "arranca Mongo sin esperar a que el nombre sea suyo:\n" + c[:120]
        # Lo que se compara: el nombre resuelto contra las direcciones de ESTE
        # contenedor. Resolverlo nomás no alcanza: el 25 de septiembre el
        # nombre resolvía, al contenedor viejo.
        assert "networkInterfaces()" in c and "lookup(\\\"$RAILWAY_PRIVATE_DOMAIN\\\"" in c
        assert "NOMBRE CONFIRMADO" in c


def test_LA_ESPERA_TIENE_TOPE_Y_ARRANCA_IGUAL():
    """Sin tope, una red privada mal configurada dejaría a Mongo sin arrancar
    nunca, que es peor que arrancar y avisar."""
    for c in _comandos():
        tope = re.search(r"if \[ \$N -ge (\d+) \]; then echo \"NOMBRE SIN CONFIRMAR[^\"]*\"; break; fi; sleep (\d+)", c)
        assert tope, "la espera no tiene tope, o al llegar no arranca igual:\n" + c[:120]
        segundos = int(tope.group(1)) * int(tope.group(2))
        assert 60 <= segundos <= 300, f"el tope es de {segundos} s"
