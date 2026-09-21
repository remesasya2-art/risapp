"""
tests/_nucleo_comun.py — lo que comparten los tests del núcleo.

    Desde N4 una cuenta de pago sólo se abre a un titular con legajo
    aprobado y vigente. Los tests del libro, la cola y los rieles no son
    sobre el legajo, así que acá se les da uno de una vez: un CPF de prueba
    distinto por nombre, siempre el mismo para el mismo nombre.
"""
import asyncio
import hashlib


def _ya(c):
    return asyncio.run(c)


def cpf_para(nombre: str) -> str:
    """Un CPF de prueba válido y estable a partir de un nombre."""
    from nucleo.identidad.simulador import cpf_de_prueba
    base9 = str(int(hashlib.md5(nombre.encode("utf-8")).hexdigest(), 16) % 10 ** 9).zfill(9)
    if len(set(base9)) == 1:                              # once dígitos iguales no son un CPF
        base9 = base9[:-1] + ("1" if base9[-1] != "1" else "2")
    return cpf_de_prueba(base9)


def titular_aprobado(nombre: str = "u_ana") -> str:
    from nucleo.identidad import legajos
    return _ya(legajos.alta_aprobada_de_prueba(documento=cpf_para(nombre), nombre=f"Titular {nombre}"))


def cuenta_aprobada(nombre: str = "u_ana") -> str:
    """Una cuenta de pago para un titular recién aprobado. Devuelve su id."""
    from nucleo import comandos
    return _ya(comandos.crear_cuenta(titular_ref=titular_aprobado(nombre)))["id"]


def cuenta_por_http(cliente, nombre: str = "u_ana") -> str:
    """El mismo camino, pero por las rutas: titular, verificar, cruzar,
    aprobar, cuenta. Devuelve el id de la cuenta."""
    t = cliente.post("/api/nucleo/laboratorio/identidad/titulares",
                     json={"documento": cpf_para(nombre), "nombre": f"Titular {nombre}", "origen_de_fondos": "salario"})
    assert t.status_code == 200, t.text
    tid = t.json()["id"]
    if t.json()["estado"] != "aprobado":
        assert cliente.post(f"/api/nucleo/laboratorio/identidad/titulares/{tid}/verificar").status_code == 200
        assert cliente.post(f"/api/nucleo/laboratorio/identidad/titulares/{tid}/cruzar").status_code == 200
        a = cliente.post(f"/api/nucleo/laboratorio/identidad/titulares/{tid}/aprobar", json={"nivel_de_riesgo": "bajo"})
        assert a.status_code == 200, a.text
    r = cliente.post("/api/nucleo/laboratorio/cuentas", json={"titular": tid})
    assert r.status_code == 200, r.text
    return r.json()["id"]
