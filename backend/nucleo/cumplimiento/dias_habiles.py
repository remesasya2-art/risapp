"""
Días hábiles de Brasil.

    Un plazo «de diez días hábiles» se cuenta sin sábados, domingos ni
    feriados nacionales. Los feriados fijos están en una lista; los móviles
    (Carnaval, Viernes Santo, Corpus Christi) se calculan desde la Pascua
    con el algoritmo de Meeus, que es el que usa todo el mundo.

    No están los feriados estaduales ni municipales: el regulador cuenta
    con los nacionales. Si un día alguien necesita el de una ciudad, se
    agrega acá y en ningún otro lado.
"""
from datetime import date, timedelta

FERIADOS_FIJOS = ((1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25))


def pascua(anio: int) -> date:
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def feriados(anio: int) -> set:
    p = pascua(anio)
    moviles = {p - timedelta(days=48), p - timedelta(days=47),     # lunes y martes de Carnaval
               p - timedelta(days=2),                              # Viernes Santo
               p + timedelta(days=60)}                             # Corpus Christi
    return {date(anio, m, d) for m, d in FERIADOS_FIJOS} | moviles


def es_habil(d: date) -> bool:
    return d.weekday() < 5 and d not in feriados(d.year)


def siguiente_habil(d: date) -> date:
    """El primer día hábil DESPUÉS de `d`."""
    d = d + timedelta(days=1)
    while not es_habil(d):
        d += timedelta(days=1)
    return d


def sumar_habiles(d: date, n: int) -> date:
    """`n` días hábiles después de `d`. El propio `d` no cuenta."""
    for _ in range(n):
        d = siguiente_habil(d)
    return d


def ultimo_habil_del_mes(anio: int, mes: int) -> date:
    import calendar
    d = date(anio, mes, calendar.monthrange(anio, mes)[1])
    while not es_habil(d):
        d -= timedelta(days=1)
    return d
