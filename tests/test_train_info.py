"""
Unit-тесты нормализации полей поезда из ответа API РЖД.

API возвращает время в LocalDepartureDateTime/LocalArrivalDateTime и название
в TrainName, а не в DepartureTime/ArrivalTime/RouteName — эти тесты страхуют от
регресса, когда хендлеры читали несуществующие поля и показывали пустые значения.
"""
from services.rzd_api import RZDAPIService


api = RZDAPIService()


def test_extract_train_info_real_shape():
    train = {
        "TrainNumber": "770А",
        "TrainName": "САПСАН",
        "LocalDepartureDateTime": "2026-06-26T13:40:00",
        "LocalArrivalDateTime": "2026-06-26T17:40:00",
        "TripDuration": 240.0,
    }
    info = api.extract_train_info(train)
    assert info["number"] == "770А"
    assert info["name"] == "САПСАН"
    assert info["departure"] == "13:40"
    assert info["arrival"] == "17:40"
    assert info["duration"] == "4ч"


def test_extract_train_info_missing_fields():
    info = api.extract_train_info({})
    assert info["number"] == "N/A"
    assert info["name"] == ""
    assert info["departure"] == ""
    assert info["arrival"] == ""
    assert info["duration"] == ""


def test_extract_train_info_fallbacks():
    # Нет TrainName/TrainNumber — берём запасные поля
    train = {
        "DisplayTrainNumber": "020У",
        "TrainDescription": "ФИРМ",
        "LocalDepartureDateTime": "2026-01-01T00:05:00",
    }
    info = api.extract_train_info(train)
    assert info["number"] == "020У"
    assert info["name"] == "ФИРМ"
    assert info["departure"] == "00:05"
    assert info["arrival"] == ""


def test_format_duration():
    assert RZDAPIService.format_duration(240) == "4ч"
    assert RZDAPIService.format_duration(245) == "4ч 5м"
    assert RZDAPIService.format_duration(45) == "45м"
    assert RZDAPIService.format_duration(0) == ""
    assert RZDAPIService.format_duration(None) == ""
    assert RZDAPIService.format_duration("abc") == ""


def _train_with_cars():
    return {
        "CarGroups": [
            {"AvailabilityIndication": "Available", "PlaceQuantity": 10,
             "LowerPlaceQuantity": 6, "UpperPlaceQuantity": 4,
             "MinPrice": 3500.0, "CarTypeName": "Купе"},
            {"AvailabilityIndication": "Available", "PlaceQuantity": 5,
             "LowerPlaceQuantity": 5, "UpperPlaceQuantity": 0,
             "MinPrice": 2200.0, "CarTypeName": "Плац"},
            {"AvailabilityIndication": "NotAvailable", "PlaceQuantity": 99,
             "MinPrice": 100.0, "CarTypeName": "Люкс"},
        ]
    }


def test_count_seats_breakdown():
    b = api.count_seats_breakdown(_train_with_cars())
    assert b["total"] == 15          # 10 + 5, недоступный вагон не считается
    assert b["lower"] == 11          # 6 + 5
    assert b["upper"] == 4
    assert b["types"] == {"Купе": 10, "Плац": 5}


def test_count_seats_breakdown_empty():
    b = api.count_seats_breakdown({})
    assert b == {"total": 0, "lower": 0, "upper": 0, "types": {}}


def test_min_price():
    assert api.min_price(_train_with_cars()) == 2200.0      # дешевле из доступных
    assert api.min_price({}) is None
    assert api.min_price({"CarGroups": [
        {"AvailabilityIndication": "NotAvailable", "MinPrice": 100.0}
    ]}) is None


def test_build_purchase_url():
    # без имён резолв nodeId пропускается (без сети) -> фолбэк на коды, дата ISO, ?adult
    url = api.build_purchase_url("2000000", "2004000", "2026-06-26T00:00:00")
    assert url == "https://ticket.rzd.ru/searchresults/v/1/2000000/2004000/2026-06-26?adult=1"
    url2 = api.build_purchase_url("2000000", "2004000", "2026-06-26T00:00:00", adult=2)
    assert url2.endswith("/2000000/2004000/2026-06-26?adult=2")


def test_resolve_node_id_no_name_returns_empty():
    # пустое имя -> без сетевого запроса, пустой результат
    assert api.resolve_node_id("2000000", "") == ""
