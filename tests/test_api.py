import os
import json
import requests
import pytest

from dotenv import load_dotenv

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

    response = requests.get(suggest_url, params=params, headers=headers, timeout=30)
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

    response = requests.get(api_url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    assert isinstance(data, dict)
    assert 'Trains' in data


