"""Тесты фильтр-осведомлённого мониторинга (_filtered_state)"""
from datetime import datetime

from services.monitoring import MonitoringService
from services.rzd_api import RZDAPIService
from database import Subscription


def _sub(**kw):
    base = dict(id=1, user_id=1, origin_code="A", origin_name="A", destination_code="B",
                destination_name="B", departure_date="2026-07-01T00:00:00", train_numbers="",
                car_types="", min_seats=1, adult_passengers=1, children_passengers=0,
                interval_minutes=5, is_active=True, created_at=datetime.now(),
                berth="any", max_price=0)
    base.update(kw)
    return Subscription(**base)


def _trains():
    return [{"TrainNumber": "001A", "CarGroups": [
        {"AvailabilityIndication": "Available", "CarType": "Compartment", "CarTypeName": "Купе",
         "PlaceQuantity": 4, "LowerPlaceQuantity": 2, "UpperPlaceQuantity": 2, "MinPrice": 9000.0},
        {"AvailabilityIndication": "Available", "CarType": "ReservedSeat", "CarTypeName": "Плац",
         "PlaceQuantity": 5, "LowerPlaceQuantity": 5, "UpperPlaceQuantity": 0, "MinPrice": 2000.0},
    ]}]


def test_filtered_state_price_cap():
    api = RZDAPIService()
    trains, state = MonitoringService._filtered_state(api, _sub(max_price=3000), _trains())
    assert len(trains) == 1                  # есть подходящие (Плац 2000<=3000)
    assert state == "001A:5"                 # под фильтр 5 мест


def test_filtered_state_none_match():
    api = RZDAPIService()
    trains, state = MonitoringService._filtered_state(api, _sub(car_types="Soft"), _trains())
    assert trains == [] and state == "001A:0"
