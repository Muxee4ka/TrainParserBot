"""Детализация в уведомлениях и переиспользование схемы вагонов (#8)."""
from datetime import datetime

import services.rzd_seatmap as seatmap
from services.monitoring import MonitoringService
from services.rzd_api import RZDAPIService
from database import Subscription


def _sub(**kw):
    base = dict(id=1, user_id=1, origin_code="2000000", origin_name="Москва",
                destination_code="2060000", destination_name="Ярославль",
                departure_date="2026-09-21T00:00:00", train_numbers="", car_types="",
                min_seats=1, adult_passengers=1, children_passengers=0, interval_minutes=5,
                is_active=True, created_at=datetime.now(), berth="any", max_price=0,
                include_disabled=False)
    base.update(kw)
    return Subscription(**base)


def _trains():
    return [{
        "TrainNumber": "063В", "DisplayTrainNumber": "063В", "Provider": "P1",
        "LocalDepartureDateTime": "2026-09-21T01:26:00",
        "CarGroups": [
            {"AvailabilityIndication": "Available", "CarType": "Compartment",
             "CarTypeName": "КУПЕ", "TotalPlaceQuantity": 2, "LowerPlaceQuantity": 1,
             "UpperPlaceQuantity": 1, "MinPrice": 3752.6},
        ],
    }]


PAYLOAD = {"Cars": [
    {"CarNumber": "08", "CarType": "Compartment", "CarTypeName": "КУПЕ",
     "ServiceClassNameRu": "", "CarPlaceNameRu": "Нижнее",
     "MinPrice": 3752.6, "MaxPrice": 3752.6, "IsForDisabledPersons": False,
     "FreePlacesByCompartments": [{"CompartmentNumber": 4, "Places": "015"}]},
    {"CarNumber": "11", "CarType": "Compartment", "CarTypeName": "КУПЕ",
     "ServiceClassNameRu": "", "CarPlaceNameRu": "Нижнее",
     "MinPrice": 2452.2, "MaxPrice": 2452.2, "IsForDisabledPersons": True,
     "FreePlacesByCompartments": [{"CompartmentNumber": 1, "Places": "001"}]},
]}


def _count_fetches(monkeypatch):
    """Подменяет сетевой _fetch и считает обращения."""
    calls = []

    def fake(self, *a, **kw):
        calls.append(a)
        return PAYLOAD

    monkeypatch.setattr(seatmap.SeatMapService, "_fetch", fake)
    return calls


def test_notification_details_plain_filter(monkeypatch):
    """Обычный фильтр (не cabin/pair/together) тоже получает вагон и место."""
    _count_fetches(monkeypatch)
    svc = MonitoringService.__new__(MonitoringService)
    svc.rzd_api = RZDAPIService()
    msg = svc.format_availability_message(_sub(berth="lower"), _trains())
    assert "Вагон 08" in msg
    assert "015" in msg
    assert "3752" in msg


def test_notification_hides_disabled_seats(monkeypatch):
    _count_fetches(monkeypatch)
    svc = MonitoringService.__new__(MonitoringService)
    svc.rzd_api = RZDAPIService()
    assert "Вагон 11" not in svc.format_availability_message(_sub(berth="lower"), _trains())
    assert "Вагон 11" in svc.format_availability_message(
        _sub(berth="lower", include_disabled=True), _trains())


def test_seatmap_fetched_once_per_train(monkeypatch):
    """Раньше count_matched и format_availability_message били по сети отдельно."""
    calls = _count_fetches(monkeypatch)
    api = RZDAPIService()
    sub = _sub(berth="cabin")
    cache = {}
    MonitoringService._filtered_state(api, sub, _trains(), cache)
    svc = MonitoringService.__new__(MonitoringService)
    svc.rzd_api = api
    svc.format_availability_message(sub, _trains(), cache)
    assert len(calls) == 1, f"ожидался один запрос схемы, было {len(calls)}"


def test_network_failure_degrades_to_counts_only(monkeypatch):
    """Схема недоступна — уведомление всё равно уходит, без детализации."""
    def boom(self, *a, **kw):
        raise RuntimeError("CarPricing недоступен")

    monkeypatch.setattr(seatmap.SeatMapService, "_fetch", boom)
    svc = MonitoringService.__new__(MonitoringService)
    svc.rzd_api = RZDAPIService()
    msg = svc.format_availability_message(_sub(berth="lower"), _trains())
    assert "063В" in msg
    assert "Вагон" not in msg
