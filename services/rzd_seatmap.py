"""Подсчёт полностью свободных купе через схему вагонов РЖД (CarPricing).

Агрегатное поле EmptyCabinQuantity из train-pricing ненадёжно (возвращает 0,
когда пустые купе реально есть). Достоверный источник — эндпоинт CarPricing,
который отдаёт свободные места, сгруппированные по купе (FreePlacesByCompartments).
Один физический вагон в ответе разбит на несколько строк (разные тарифы) — их
объединяем по CarNumber, а места внутри купе — по CompartmentNumber. Купе считаем
полностью свободным, если в нём свободны все 4 места.

Это сетевой запрос на поезд, поэтому используется только под фильтр «купе целиком»
(berth='cabin'), не в общем цикле мониторинга остальных подписок.
"""
import logging
from collections import defaultdict

import requests

from config import config

logger = logging.getLogger(__name__)

CAR_PRICING_URL = (
    "https://ticket.rzd.ru/apib2b/p/Railway/V1/Search/CarPricing"
    "?service_provider=B2B_RZD&isBonusPurchase=false"
)
# Количество мест в стандартном купе
COMPARTMENT_SIZE = 4


def empty_compartments_detail(payload: dict) -> list:
    """Список полностью свободных купе с номерами мест.

    Объединяет строки одного вагона (CarNumber) и места внутри купе
    (CompartmentNumber); купе считается пустым, если свободны все 4 места.
    Возвращает [{'car': '27', 'compartment': '3', 'places': [9,10,11,12]}, ...],
    отсортированный по вагону и купе. Только купейные вагоны.
    """
    try:
        # car_number -> compartment_number -> множество свободных мест
        cars = defaultdict(lambda: defaultdict(set))
        for car in payload.get("Cars") or []:
            if car.get("CarType") != "Compartment":
                continue
            number = car.get("CarNumber")
            for blk in car.get("FreePlacesByCompartments") or []:
                comp = blk.get("CompartmentNumber")
                for p in str(blk.get("Places", "")).split(","):
                    p = p.strip()
                    if p.isdigit():
                        cars[number][comp].add(int(p))
        result = []
        for number, compartments in cars.items():
            for comp, places in compartments.items():
                if len(places) >= COMPARTMENT_SIZE:
                    result.append({"car": number, "compartment": comp, "places": sorted(places)})

        def _key(d):
            def _int(v):
                return int(v) if str(v).isdigit() else 0
            return (_int(d["car"]), _int(d["compartment"]))
        result.sort(key=_key)
        return result
    except Exception as e:
        logger.error(f"Ошибка разбора пустых купе: {e}")
        return []


def count_empty_compartments(payload: dict) -> int:
    """Число полностью свободных купе (см. empty_compartments_detail)."""
    return len(empty_compartments_detail(payload))


def format_empty_cabins(detail: list, limit: int = 6) -> str:
    """Человекочитаемый список пустых купе: 'вагон 27: купе 1, 3, 4'."""
    by_car = defaultdict(list)
    for d in detail[:limit]:
        by_car[d["car"]].append(str(d["compartment"]))
    parts = [f"вагон {car}: купе {', '.join(comps)}" for car, comps in by_car.items()]
    tail = f" и ещё {len(detail) - limit}" if len(detail) > limit else ""
    return "; ".join(parts) + tail


class SeatMapService:
    """Обёртка над эндпоинтом схемы вагонов РЖД (CarPricing)."""

    def __init__(self):
        self.user_agent = config.USER_AGENT

    def _fetch(self, origin_code: str, destination_code: str, departure_datetime: str,
               train_number: str, provider: str = "P1") -> dict:
        """POST к CarPricing. departure_datetime — ЛОКАЛЬНОЕ время отправления
        (LocalDepartureDateTime поезда, с часами, а не полночь)."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "Origin": "https://ticket.rzd.ru",
            "Referer": "https://ticket.rzd.ru/",
        }
        body = {
            "OriginCode": origin_code,
            "DestinationCode": destination_code,
            "Provider": provider or "P1",
            "DepartureDate": departure_datetime,
            "TrainNumber": train_number,
            "SpecialPlacesDemand": "StandardPlacesAndForDisabledPersons",
            "OnlyFpkBranded": False,
            "HasPlacesForLargeFamily": False,
            "CarIssuingType": "Passenger",
        }
        resp = requests.post(CAR_PRICING_URL, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def empty_compartments_detail(self, origin_code: str, destination_code: str,
                                  departure_datetime: str, train_number: str,
                                  provider: str = "P1"):
        """Список пустых купе с номерами мест или None при сетевой ошибке."""
        try:
            return empty_compartments_detail(
                self._fetch(origin_code, destination_code, departure_datetime, train_number, provider)
            )
        except Exception as e:
            logger.error(f"Схема вагонов недоступна ({train_number}): {e}")
            return None

    def empty_compartments(self, origin_code: str, destination_code: str,
                           departure_datetime: str, train_number: str,
                           provider: str = "P1"):
        """Число полностью свободных купе поезда или None при сетевой ошибке."""
        detail = self.empty_compartments_detail(
            origin_code, destination_code, departure_datetime, train_number, provider
        )
        return None if detail is None else len(detail)
