"""
Los períodos de los reportes, escritos como texto corto y sin ambigüedad.

    «2026-09»     un mes        (balancete)
    «2026-09-21»  un día        (CCS)
    «2026-S2»     un semestre   (e-Financeira, informe de ouvidoria)
    «2026»        un año        (informe anual de incidentes)

    Cada uno se convierte en su primer y último día. Lo demás del paquete
    trabaja con fechas; el texto es para las personas y para la clave única
    de la tabla.
"""
import calendar
import re
from datetime import date, timedelta

MES, DIA, SEMESTRE, ANIO = "mes", "dia", "semestre", "anio"


class PeriodoInvalido(ValueError):
    pass


def limites(clase: str, periodo: str) -> tuple:
    """(primer día, último día) del período, o PeriodoInvalido."""
    try:
        if clase == MES and re.fullmatch(r"\d{4}-\d{2}", periodo):
            a, m = int(periodo[:4]), int(periodo[5:7])
            return date(a, m, 1), date(a, m, calendar.monthrange(a, m)[1])
        if clase == DIA and re.fullmatch(r"\d{4}-\d{2}-\d{2}", periodo):
            d = date.fromisoformat(periodo)
            return d, d
        if clase == SEMESTRE and re.fullmatch(r"\d{4}-S[12]", periodo):
            a = int(periodo[:4])
            return (date(a, 1, 1), date(a, 6, 30)) if periodo.endswith("1") else (date(a, 7, 1), date(a, 12, 31))
        if clase == ANIO and re.fullmatch(r"\d{4}", periodo):
            a = int(periodo)
            return date(a, 1, 1), date(a, 12, 31)
    except ValueError:
        pass
    raise PeriodoInvalido(f"«{periodo}» no es un período de clase {clase}.")


def mes_de(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def semestre_de(d: date) -> str:
    return f"{d.year:04d}-S{1 if d.month <= 6 else 2}"


def meses_entre(desde: date, hasta: date) -> list:
    """Los meses «YYYY-MM» de desde a hasta, inclusive."""
    salida, a, m = [], desde.year, desde.month
    while (a, m) <= (hasta.year, hasta.month):
        salida.append(f"{a:04d}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return salida


def semestres_entre(desde: date, hasta: date) -> list:
    salida = []
    for mes in meses_entre(desde, hasta):
        s = semestre_de(date(int(mes[:4]), int(mes[5:7]), 1))
        if s not in salida:
            salida.append(s)
    return salida


def dias_entre(desde: date, hasta: date) -> list:
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
