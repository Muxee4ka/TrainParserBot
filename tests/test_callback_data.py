import pytest

from services.rzd_api import RZDAPIService


def clean_callback_name(name: str) -> str:
    return name.replace('(', '').replace(')', '').replace('-', ' ').replace('_', ' ')[:30]


def build_callback(station_code: str, station_name: str) -> str:
    service = RZDAPIService()
    # mimic internal creation but without API calls
    clean_name = clean_callback_name(station_name)
    cb = f"station_{station_code}_{clean_name}" if station_name and station_code else f"station_{station_code}"
    if len(cb.encode('utf-8')) > 64:
        cb = f"station_{station_code}"
    return cb


def parse_callback(cb: str):
    if not cb.startswith("station_"):
        raise ValueError("invalid format")
    parts = cb.split("_", 2)
    if len(parts) < 2:
        raise ValueError("invalid parts")
    station_code = parts[1]
    station_name = parts[2] if len(parts) > 2 else station_code
    return station_code, station_name


def test_callback_validation_and_parsing():
    cases = [
        ("2000003", "Москва Казанская (Казанский вокзал)"),
        ("2004001", "Санкт-Петербург-Главный (Московский вокзал)"),
        ("2060500", "Казань Пасс"),
        ("1234567", "Очень длинное название станции с множеством символов и пробелов"),
        ("9999999", "Станция с символами: ()-_,.!@#$%")
    ]
    for code, name in cases:
        cb = build_callback(code, name)
        assert len(cb.encode('utf-8')) <= 64
        parsed_code, parsed_name = parse_callback(cb)
        assert parsed_code == code
        assert isinstance(parsed_name, str)
        assert len(parsed_name) > 0


def test_callback_fallback_when_too_long():
    code = "8888888"
    # Используем не-ASCII символы, чтобы 30 символов после усечения превысили лимит 64 байта
    name = "Ж" * 200  # 30 Ж ~ 60 байт + префикс > 64
    cb = build_callback(code, name)
    assert cb == f"station_{code}"
    parsed_code, parsed_name = parse_callback(cb)
    assert parsed_code == code
    assert parsed_name == code
