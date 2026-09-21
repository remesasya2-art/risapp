"""
tests/test_nucleo_pestana_del_panel.py — la pestaña «Núcleo (laboratorio)»
del panel es sólo del super administrador.

    El servidor ya contesta 404 a todo con el núcleo apagado y exige el super
    administrador con el núcleo prendido; esto sostiene que la pestaña no
    aparezca en el menú de un administrador común ni de un agente.
"""
import os
import pathlib
import re

_SRC = pathlib.Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))) / "frontend" / "src"


def test_la_pestana_del_panel_es_solo_del_super_administrador():
    panel = (_SRC / "pages" / "AdminPanel.jsx").read_text(encoding="utf-8")
    m = re.search(r"\{\s*key:\s*'nucleo'[^}]*\}", panel)
    assert m, "no está la pestaña «nucleo» en TABS"
    assert "superAdminOnly: true" in m.group(0)
