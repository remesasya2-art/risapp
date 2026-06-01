"""
Rate Engine: applies automatic off-hours adjustments to exchange rates.

Logic:
- Work hours: configurable (default Mon-Sat 08:00-22:00 America/Caracas)
- Off hours: nights + Sundays + Venezuelan holidays (fixed + Easter-relative)
- BRL->VES (ris_to_ves): subtract `delta_brl_ves` when off-hours
- VES->BRL (ves_to_ris_rate): add `delta_ves_brl` when off-hours
"""
from datetime import datetime, timedelta, timezone, date as date_cls
from dateutil.easter import easter

CARACAS_TZ = timezone(timedelta(hours=-4))

# Fixed Venezuelan holidays (month, day)
VE_FIXED_HOLIDAYS = {
    (1, 1),    # Año Nuevo
    (4, 19),   # Declaración de Independencia
    (5, 1),    # Día del Trabajador
    (6, 24),   # Batalla de Carabobo
    (7, 5),    # Día de la Independencia
    (7, 24),   # Natalicio de Simón Bolívar
    (10, 12),  # Día de la Resistencia Indígena
    (12, 24),  # Nochebuena
    (12, 25),  # Navidad
    (12, 31),  # Fin de Año
}


def get_ve_holidays_for_year(year: int) -> set[date_cls]:
    """Return all Venezuelan holidays for a given year (fixed + Easter-relative)."""
    holidays = {date_cls(year, m, d) for (m, d) in VE_FIXED_HOLIDAYS}
    # Easter-relative
    e = easter(year)
    holidays.add(e - timedelta(days=48))  # Lunes de Carnaval
    holidays.add(e - timedelta(days=47))  # Martes de Carnaval
    holidays.add(e - timedelta(days=3))   # Jueves Santo
    holidays.add(e - timedelta(days=2))   # Viernes Santo
    return holidays


DEFAULT_CONFIG = {
    "enabled": False,
    "work_start_hour": 8,
    "work_end_hour": 22,
    "work_days": [0, 1, 2, 3, 4, 5],  # Mon-Sat (0=Mon, 6=Sun)
    "delta_brl_ves": 2.0,  # BRL->VES: subtract this from base off-hours
    "delta_ves_brl": 3.0,  # VES->BRL: add this to base off-hours
}


def caracas_now() -> datetime:
    return datetime.now(CARACAS_TZ)


def is_ve_holiday(d: date_cls) -> bool:
    return d in get_ve_holidays_for_year(d.year)


def is_off_hours(config: dict, now: datetime = None) -> bool:
    """Determine whether the current Caracas moment is off work-hours."""
    now = now or caracas_now()
    # Holiday → off-hours all day
    if is_ve_holiday(now.date()):
        return True
    # Not a working day (Sunday by default)
    if now.weekday() not in config.get("work_days", DEFAULT_CONFIG["work_days"]):
        return True
    # Outside working window
    hour = now.hour
    if hour < config.get("work_start_hour", 8):
        return True
    if hour >= config.get("work_end_hour", 22):
        return True
    return False


def apply_rate_adjustment(base_rates: dict, config: dict, now: datetime = None) -> dict:
    """Return a dict with the effective rate values and metadata.
    base_rates keys: ris_to_ves, ves_to_ris_rate, brl_to_ris, ...
    """
    if not config.get("enabled"):
        return {
            **base_rates,
            "is_off_hours": is_off_hours(config, now),
            "auto_rate_enabled": False,
        }

    off = is_off_hours(config, now)
    effective = dict(base_rates)

    if off:
        delta_bv = float(config.get("delta_brl_ves", DEFAULT_CONFIG["delta_brl_ves"]))
        delta_vb = float(config.get("delta_ves_brl", DEFAULT_CONFIG["delta_ves_brl"]))

        if "ris_to_ves" in effective and effective["ris_to_ves"] is not None:
            effective["ris_to_ves"] = round(float(effective["ris_to_ves"]) - delta_bv, 4)

        if "ves_to_ris_rate" in effective and effective["ves_to_ris_rate"] is not None:
            effective["ves_to_ris_rate"] = round(float(effective["ves_to_ris_rate"]) + delta_vb, 4)

    return {
        **effective,
        "is_off_hours": off,
        "auto_rate_enabled": True,
    }


async def load_auto_rate_config(db) -> dict:
    """Load auto-rate config from DB or return defaults."""
    doc = await db.app_settings.find_one({"setting_id": "auto_rate"}, {"_id": 0})
    if not doc:
        return dict(DEFAULT_CONFIG)
    # Merge with defaults for backward compat
    merged = dict(DEFAULT_CONFIG)
    for k in ["enabled", "work_start_hour", "work_end_hour", "work_days", "delta_brl_ves", "delta_ves_brl"]:
        if k in doc:
            merged[k] = doc[k]
    return merged
