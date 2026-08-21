"""Детализация мест для уведомлений (#8): вагон, место, полка, цена.

Строка Cars — это не вагон, а (вагон × тип полки × ценовая корзина): в живых
данных 20 строк на 6 вагонов. MinPrice внутри строки не всегда равен MaxPrice
(14 строк из 187 на проверенной выборке), поэтому цена показывается точной
только при совпадении, иначе «от N ₽».
"""
from services.rzd_seatmap import TrainSeats, SeatMapService


def _car(number, place_name, places, mn, mx=None, disabled=False, car_type="Compartment",
         type_name="КУПЕ", service_class="2Э", compartment=1):
    return {
        "CarNumber": number,
        "CarType": car_type,
        "CarTypeName": type_name,
        "ServiceClassNameRu": service_class,
        "CarPlaceNameRu": place_name,
        "MinPrice": mn,
        "MaxPrice": mn if mx is None else mx,
        "IsForDisabledPersons": disabled,
        "FreePlacesByCompartments": [{"CompartmentNumber": compartment, "Places": places}],
    }


PAYLOAD = {"Cars": [
    _car("08", "Нижнее", "015", 3752.6, compartment=4),
    _car("08", "Верхнее", "016", 2573.6, 3015.7, compartment=4),
    _car("11", "Нижнее", "001", 2452.2, disabled=True, compartment=1),
]}


def test_places_carry_car_seat_berth_and_price():
    p = TrainSeats(PAYLOAD).places(berth='lower')
    assert len(p) == 1
    assert p[0]["car"] == "08"
    assert p[0]["place"] == 15
    assert p[0]["berth"] == "lower"
    assert p[0]["min_price"] == 3752.6


def test_describe_exact_price_when_min_equals_max():
    s = TrainSeats(PAYLOAD).describe(berth='lower')
    assert "Вагон 08" in s
    assert "015" in s
    assert "3752" in s
    assert "от 3752" not in s


def test_describe_uses_ot_when_price_spread():
    s = TrainSeats(PAYLOAD).describe(berth='upper')
    assert "от 2573" in s


def test_describe_hides_disabled_by_default():
    """Инвалидные места не должны попадать в детализацию (#9)."""
    assert "Вагон 11" not in TrainSeats(PAYLOAD).describe(berth='any')
    assert "Вагон 11" in TrainSeats(PAYLOAD).describe(berth='any', include_disabled=True)


def test_places_respect_max_price():
    assert TrainSeats(PAYLOAD).places(berth='any', max_price=3000) != []
    assert TrainSeats(PAYLOAD).places(berth='any', max_price=100) == []


def test_describe_limits_output():
    many = {"Cars": [_car("05", "Нижнее", ",".join(str(i) for i in range(1, 21)), 1000)]}
    s = TrainSeats(many).describe(berth='lower', limit=3)
    assert s.count("Место") == 3
    assert "ещё" in s


def test_empty_payload_is_safe():
    assert TrainSeats({}).places() == []
    assert TrainSeats({}).describe(berth='any') == ""


def test_seats_returns_none_on_network_error(monkeypatch):
    svc = SeatMapService()

    def boom(*a, **kw):
        raise RuntimeError("CarPricing недоступен")

    monkeypatch.setattr(svc, "_fetch", boom)
    assert svc.seats("2000000", "2060000", "2026-09-21T01:26:00", "063В") is None


def test_seats_returns_trainseats_on_success(monkeypatch):
    svc = SeatMapService()
    monkeypatch.setattr(svc, "_fetch", lambda *a, **kw: PAYLOAD)
    s = svc.seats("2000000", "2060000", "2026-09-21T01:26:00", "063В")
    assert isinstance(s, TrainSeats)
    assert s.places(berth='lower')[0]["car"] == "08"


def test_legacy_methods_still_work(monkeypatch):
    """Старые четыре метода сохраняют сигнатуры — их зовут существующие вызывающие."""
    svc = SeatMapService()
    monkeypatch.setattr(svc, "_fetch", lambda *a, **kw: PAYLOAD)
    args = ("2000000", "2060000", "2026-09-21T01:26:00", "063В")
    assert svc.detail_for_berth('cabin', *args) is not None
    assert svc.count_for_berth('cabin', *args) is not None
    assert svc.empty_compartments_detail(*args) is not None
    assert svc.empty_compartments(*args) is not None
