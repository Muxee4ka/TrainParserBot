"""Best-effort определение мест «у окна» через схему вагона РЖД.

Используется ТОЛЬКО при просмотре/подписке, никогда в цикле мониторинга.
Эндпоинт car-pricing требует доревёрса параметров; до этого _fetch может
возвращать пустое/ошибку, а публичные функции — None (UI показывает «н/д»).
"""
import logging
import requests

from config import config

logger = logging.getLogger(__name__)

CAR_PRICING_URL = "https://ticket.rzd.ru/api/v1/railway-service/prices/car-pricing"


def parse_window_counts(payload: dict):
    """Считает доступные места у окна / не у окна из схемы вагона.

    Возвращает None, если форма ответа не распознана (тогда UI -> «н/д»).
    """
    try:
        cars = payload.get("Cars")
        if not cars:
            return None
        window = other = 0
        seen = False
        for car in cars:
            for pl in car.get("Places", []) or []:
                if "Window" not in pl:
                    continue
                seen = True
                if not pl.get("IsAvailable", True):
                    continue
                if pl.get("Window"):
                    window += 1
                else:
                    other += 1
        if not seen:
            return None
        return {"window": window, "other": other}
    except Exception as e:
        logger.error(f"Ошибка парсинга схемы мест: {e}")
        return None


class SeatMapService:
    """Обёртка над car-pricing РЖД (best-effort)."""

    def __init__(self):
        self.user_agent = config.USER_AGENT

    def _fetch(self, train_number, car_type, origin, destination, departure_date) -> dict:
        params = {
            "service_provider": "B2B_RZD",
            "getByLocalTime": "true",
            "origin": origin,
            "destination": destination,
            "departureDate": departure_date,
            "trainNumber": train_number,
            "carType": car_type,
            "specialPlacesDemand": "StandardPlacesAndForDisabledPersons",
            "carIssuingType": "Passenger",
            "adultPassengersQuantity": 1,
        }
        headers = {"Accept": "application/json, text/plain, */*", "User-Agent": self.user_agent}
        resp = requests.get(CAR_PRICING_URL, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_window_counts(self, train_number, car_type, origin, destination, departure_date):
        """Возвращает {'window':int,'other':int} или None (best-effort)."""
        try:
            return parse_window_counts(self._fetch(train_number, car_type, origin, destination, departure_date))
        except Exception as e:
            logger.error(f"Схема мест недоступна: {e}")
            return None
