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


def count_empty_compartments(payload: dict) -> int:
    """Считает полностью свободные купе по ответу CarPricing.

    Объединяет строки одного вагона (CarNumber) и места внутри купе
    (CompartmentNumber), затем считает купе, где свободны все 4 места.
    Учитываются только купейные вагоны (CarType == 'Compartment').
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
        total = 0
        for compartments in cars.values():
            total += sum(1 for places in compartments.values() if len(places) >= COMPARTMENT_SIZE)
        return total
    except Exception as e:
        logger.error(f"Ошибка подсчёта пустых купе: {e}")
        return 0


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

    def empty_compartments(self, origin_code: str, destination_code: str,
                           departure_datetime: str, train_number: str,
                           provider: str = "P1"):
        """Число полностью свободных купе поезда или None при сетевой ошибке."""
        try:
            return count_empty_compartments(
                self._fetch(origin_code, destination_code, departure_datetime, train_number, provider)
            )
        except Exception as e:
            logger.error(f"Схема вагонов недоступна ({train_number}): {e}")
            return None
