"""Анализ схемы вагонов РЖД (CarPricing) для фильтров, требующих расположения мест.

Агрегатные поля train-pricing не дают: какие конкретно места свободны, нижние они
или верхние, и в каком купе. Достоверный источник — эндпоинт CarPricing: он отдаёт
свободные места по купе (FreePlacesByCompartments), а вагон разбит на строки по типу
полки (CarPlaceNameRu: «Нижнее»/«Верхнее»). Объединяем строки вагона по CarNumber,
классифицируем места по типу полки и группируем по купе. Отсюда выводим:
  • пустые купе (berth='cabin') — свободны все 4 места;
  • пары низ+верх в одном купе/блоке (berth='pair') — есть и нижнее, и верхнее.

Это сетевой запрос на поезд, поэтому используется только под эти «тяжёлые» фильтры,
не в общем цикле мониторинга остальных подписок.
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
# Фильтры полки, требующие схему вагона (сетевой запрос)
SEATMAP_BERTHS = ('cabin', 'pair', 'together')


def _berth_kind(car: dict) -> str:
    """Тип полки строки вагона по CarPlaceNameRu/Type.

    Боковые места в плацкарте (37–54) отделяем от основных: для «низ+верх в одном
    купе» учитываются только основные полки купе/блока, а не боковые в проходе.
    Возвращает 'lower' | 'upper' | 'side_lower' | 'side_upper' | 'other'."""
    name = (car.get("CarPlaceNameRu") or "").lower()
    side = "боков" in name
    if "ниж" in name:
        return "side_lower" if side else "lower"
    if "верх" in name:
        return "side_upper" if side else "upper"
    t = car.get("CarPlaceType") or ""
    if t == "Lower":
        return "lower"
    if t == "Upper":
        return "upper"
    return "other"


def _car_allowed(car: dict, car_types) -> bool:
    """Подходит ли вагон под выбранные категории (CarType или класс обслуживания)."""
    if not car_types:
        return True
    return car.get("CarType") in car_types or car.get("ServiceClassNameRu") in car_types


def parse_compartments(payload: dict, car_types=None, max_price: int = 0,
                       include_types=("Compartment", "ReservedSeat")) -> dict:
    """car_number -> compartment_number -> {'lower': set, 'upper': set, 'all': set}.

    Объединяет строки одного вагона и классифицирует места по типу полки. Боковые
    места НЕ попадают в lower/upper (они не образуют купе «низ+верх»). include_types
    ограничивает типы вагонов; car_types — выбранные категории (CarType/класс);
    max_price (>0) отсекает вагоны дороже лимита (по MinPrice вагона)."""
    wanted = set(car_types) if car_types else None
    cars = defaultdict(lambda: defaultdict(lambda: {"lower": set(), "upper": set(), "all": set()}))
    try:
        for car in payload.get("Cars") or []:
            if car.get("CarType") not in include_types:
                continue
            if not _car_allowed(car, wanted):
                continue
            if max_price and (car.get("MinPrice") or 0) > max_price:
                continue
            number = car.get("CarNumber")
            kind = _berth_kind(car)
            for blk in car.get("FreePlacesByCompartments") or []:
                comp = blk.get("CompartmentNumber")
                for p in str(blk.get("Places", "")).split(","):
                    p = p.strip()
                    if not p.isdigit():
                        continue
                    p = int(p)
                    cell = cars[number][comp]
                    cell["all"].add(p)
                    # боковые (side_*) в пару «в одном купе» не идут
                    if kind in ("lower", "upper"):
                        cell[kind].add(p)
    except Exception as e:
        logger.error(f"Ошибка разбора схемы вагонов: {e}")
    return cars


def _sort_key(d):
    def _int(v):
        return int(v) if str(v).isdigit() else 0
    return (_int(d["car"]), _int(d["compartment"]))


def blocks_with_at_least(payload: dict, min_size: int, car_types=None, max_price: int = 0,
                         include_types=("Compartment",)) -> list:
    """Блоки (вагон+CompartmentNumber), где свободно >= min_size мест:
    [{'car','compartment','places':[...]}], отсортировано."""
    result = []
    comps_by_car = parse_compartments(payload, car_types=car_types, max_price=max_price,
                                      include_types=include_types)
    for number, comps in comps_by_car.items():
        for comp, cell in comps.items():
            if len(cell["all"]) >= min_size:
                result.append({"car": number, "compartment": comp, "places": sorted(cell["all"])})
    result.sort(key=_sort_key)
    return result


def empty_compartments_detail(payload: dict, car_types=None, max_price: int = 0) -> list:
    """Полностью свободные купе: [{'car','compartment','places':[...]}], отсортировано.
    Только купейные вагоны (целиком пустое купе — понятие купе)."""
    return blocks_with_at_least(payload, COMPARTMENT_SIZE, car_types=car_types, max_price=max_price,
                                include_types=("Compartment",))


def together_seats_detail(payload: dict, min_count: int, car_types=None, max_price: int = 0) -> list:
    """Блоки сидячих мест (Sedentary), где свободно >= min_count мест рядом (одна
    физическая группа кресел по CompartmentNumber). Приближение: если внутри блока
    часть мест продана, оставшиеся свободные необязательно физически смежны."""
    return blocks_with_at_least(payload, max(1, min_count), car_types=car_types, max_price=max_price,
                                include_types=("Sedentary",))


def pair_compartments_detail(payload: dict, car_types=None, max_price: int = 0) -> list:
    """Купе/блоки (купе и плац), где свободны и нижнее, и верхнее ОСНОВНЫЕ места:
    [{'car','compartment','lower':[...],'upper':[...]}], отсортировано."""
    result = []
    comps_by_car = parse_compartments(payload, car_types=car_types, max_price=max_price)
    for number, comps in comps_by_car.items():
        for comp, cell in comps.items():
            if cell["lower"] and cell["upper"]:
                result.append({
                    "car": number, "compartment": comp,
                    "lower": sorted(cell["lower"]), "upper": sorted(cell["upper"]),
                })
    result.sort(key=_sort_key)
    return result


def detail_for_berth(payload: dict, berth: str, car_types=None, max_price: int = 0,
                     min_count: int = 1) -> list:
    """Детали под нужный фильтр полки ('cabin' | 'pair' | 'together') с учётом категорий
    и цены. min_count используется только веткой 'together' (сколько мест нужно рядом)."""
    if berth == "pair":
        return pair_compartments_detail(payload, car_types=car_types, max_price=max_price)
    if berth == "together":
        return together_seats_detail(payload, min_count, car_types=car_types, max_price=max_price)
    return empty_compartments_detail(payload, car_types=car_types, max_price=max_price)


def count_empty_compartments(payload: dict) -> int:
    """Число полностью свободных купе."""
    return len(empty_compartments_detail(payload))


def format_empty_cabins(detail: list, limit: int = 6) -> str:
    """Список пустых купе: 'вагон 27: купе 1, 3, 4'."""
    by_car = defaultdict(list)
    for d in detail[:limit]:
        by_car[d["car"]].append(str(d["compartment"]))
    parts = [f"вагон {car}: купе {', '.join(comps)}" for car, comps in by_car.items()]
    tail = f" и ещё {len(detail) - limit}" if len(detail) > limit else ""
    return "; ".join(parts) + tail


def format_pairs(detail: list, limit: int = 6) -> str:
    """Список пар низ+верх: 'вагон 27: купе 3 (низ 9, верх 10)'."""
    parts = []
    for d in detail[:limit]:
        low = ", ".join(map(str, d["lower"]))
        up = ", ".join(map(str, d["upper"]))
        parts.append(f"вагон {d['car']}: купе {d['compartment']} (низ {low}, верх {up})")
    tail = f"; и ещё {len(detail) - limit}" if len(detail) > limit else ""
    return "; ".join(parts) + tail


def format_seat_groups(detail: list, limit: int = 6) -> str:
    """Список групп сидячих мест: 'вагон 06: блок 3 (3 мест: 5, 6, 8)'."""
    parts = []
    for d in detail[:limit]:
        places = ", ".join(map(str, d["places"]))
        parts.append(f"вагон {d['car']}: блок {d['compartment']} ({len(d['places'])} мест: {places})")
    tail = f"; и ещё {len(detail) - limit}" if len(detail) > limit else ""
    return "; ".join(parts) + tail


def format_seatmap_detail(berth: str, detail: list, limit: int = 6) -> str:
    """Человекочитаемый список под фильтр полки."""
    if berth == "pair":
        return format_pairs(detail, limit)
    if berth == "together":
        return format_seat_groups(detail, limit)
    return format_empty_cabins(detail, limit)


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

    def detail_for_berth(self, berth: str, origin_code: str, destination_code: str,
                         departure_datetime: str, train_number: str, provider: str = "P1",
                         car_types=None, max_price: int = 0):
        """Детали под фильтр полки ('cabin'|'pair') с учётом категорий/цены, или None при ошибке."""
        try:
            payload = self._fetch(origin_code, destination_code, departure_datetime, train_number, provider)
            return detail_for_berth(payload, berth, car_types=car_types, max_price=max_price)
        except Exception as e:
            logger.error(f"Схема вагонов недоступна ({train_number}): {e}")
            return None

    def count_for_berth(self, berth: str, origin_code: str, destination_code: str,
                        departure_datetime: str, train_number: str, provider: str = "P1",
                        car_types=None, max_price: int = 0):
        """Число подходящих купе под фильтр полки или None при сетевой ошибке."""
        detail = self.detail_for_berth(
            berth, origin_code, destination_code, departure_datetime, train_number, provider,
            car_types=car_types, max_price=max_price,
        )
        return None if detail is None else len(detail)

    # обратная совместимость для фильтра «купе целиком»
    def empty_compartments_detail(self, origin_code, destination_code, departure_datetime,
                                  train_number, provider="P1"):
        return self.detail_for_berth('cabin', origin_code, destination_code,
                                     departure_datetime, train_number, provider)

    def empty_compartments(self, origin_code, destination_code, departure_datetime,
                           train_number, provider="P1"):
        return self.count_for_berth('cabin', origin_code, destination_code,
                                    departure_datetime, train_number, provider)
