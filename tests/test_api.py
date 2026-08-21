import os
import json
import requests
import pytest

from dotenv import load_dotenv

from config import rzd_verify

load_dotenv()

RUN_INTEGRATION = os.getenv("RUN_INTEGRATION_TESTS") == "1"

pytestmark = pytest.mark.integration

@pytest.mark.skipif(not RUN_INTEGRATION, reason="Integration tests are disabled. Set RUN_INTEGRATION_TESTS=1 to enable.")
def test_station_search_integration():
    suggest_url = "https://ticket.rzd.ru/api/v1/suggests"
    params = {
        'Query': 'москва',
        'TransportType': 'bus,avia,rail,aeroexpress,suburban,boat',
        'GroupResults': 'true',
        'RailwaySortPriority': 'true',
        'SynonymOn': '1',
        'Language': 'ru'
    }
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    response = requests.get(suggest_url, params=params, headers=headers, timeout=30,
                            verify=rzd_verify())
    response.raise_for_status()
    data = response.json()

    stations = []
    if data.get('train'):
        stations.extend(data['train'])
    if data.get('city'):
        stations.extend(data['city'])
    if data.get('avia'):
        stations.extend(data['avia'])

    assert isinstance(stations, list)
    assert len(stations) >= 0


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Integration tests are disabled. Set RUN_INTEGRATION_TESTS=1 to enable.")
def test_train_search_integration():
    api_url = "https://ticket.rzd.ru/api/v1/railway-service/prices/train-pricing"
    params = {
        "service_provider": "B2B_RZD",
        "getByLocalTime": "true",
        "carGrouping": "DontGroup",
        "destination": "2060000",
        "origin": "2060440",
        "departureDate": "2025-01-15T00:00:00",
        "specialPlacesDemand": "StandardPlacesAndForDisabledPersons",
        "carIssuingType": "Passenger",
        "getTrainsFromSchedule": "true",
        "adultPassengersQuantity": 1,
        "childrenPassengersQuantity": 0,
        "hasPlacesForLargeFamily": "false"
    }
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    response = requests.get(api_url, params=params, headers=headers, timeout=30,
                            verify=rzd_verify())
    response.raise_for_status()
    data = response.json()

    assert isinstance(data, dict)
    assert 'Trains' in data


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Integration tests are disabled. Set RUN_INTEGRATION_TESTS=1 to enable.")
def test_disabled_car_group_is_wholly_disabled():
    """Инвариант, на котором стоит фильтр инвалидных мест (#9).

    Мы отбрасываем CarGroup целиком по HasPlacesForDisabledPersons, не обращаясь
    к дорогому CarPricing. Это корректно, только пока помеченная группа состоит
    ИЗ ОДНИХ инвалидных мест. Если РЖД начнёт смешивать их с обычными, дешёвый
    предикат станет отбрасывать покупаемые места — тест это поймает.
    """
    from services.rzd_api import RZDAPIService
    from services.rzd_seatmap import SeatMapService

    api, sm = RZDAPIService(), SeatMapService()
    trains = api.search_trains('2000000', '2060000', '21.09.2026')['trains']
    assert trains, "РЖД не вернул поездов — проверить маршрут/дату теста"

    checked = 0
    for train in trains[:5]:
        flagged = [g for g in (train.get('CarGroups') or [])
                   if g.get('HasPlacesForDisabledPersons')]
        if not flagged:
            continue
        seats = sm.seats('2000000', '2060000', train.get('LocalDepartureDateTime'),
                         train.get('TrainNumber'), train.get('Provider', 'P1'))
        if seats is None:
            continue
        all_places = len(seats.places(include_disabled=True))
        normal_places = len(seats.places(include_disabled=False))
        disabled_places = all_places - normal_places
        flagged_total = sum(g.get('TotalPlaceQuantity') or 0 for g in flagged)
        assert flagged_total == disabled_places, (
            f"поезд {train.get('TrainNumber')}: помеченная группа содержит "
            f"{flagged_total} мест, но инвалидных по схеме вагонов {disabled_places} — "
            f"группа перестала быть однородной, предикат в _group_allowed теперь неверен"
        )
        checked += 1

    assert checked > 0, "не нашлось ни одного поезда с инвалидной группой — тест ничего не проверил"
