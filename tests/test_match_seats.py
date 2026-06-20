from services.rzd_api import RZDAPIService

api = RZDAPIService()

def _train():
    return {"CarGroups": [
        {"AvailabilityIndication": "Available", "CarType": "Compartment", "CarTypeName": "Купе",
         "PlaceQuantity": 10, "LowerPlaceQuantity": 6, "UpperPlaceQuantity": 4,
         "LowerSidePlaceQuantity": 0, "UpperSidePlaceQuantity": 0, "MinPrice": 5200.0},
        {"AvailabilityIndication": "Available", "CarType": "ReservedSeat", "CarTypeName": "Плац",
         "PlaceQuantity": 8, "LowerPlaceQuantity": 3, "UpperPlaceQuantity": 3,
         "LowerSidePlaceQuantity": 1, "UpperSidePlaceQuantity": 1, "MinPrice": 2200.0},
        {"AvailabilityIndication": "NotAvailable", "CarType": "Soft", "CarTypeName": "Люкс",
         "PlaceQuantity": 99, "MinPrice": 100.0},
    ]}

def test_no_filters_counts_all_available():
    r = api.match_seats(_train())
    assert r["total"] == 18            # 10 + 8, недоступный не считается
    assert r["lower"] == 9             # основные нижние: 6 + 3 (боковые сюда НЕ входят)
    assert r["upper"] == 7             # основные верхние: 4 + 3
    assert r["side"] == 2              # боковые плаца: 1 + 1
    assert r["min_price"] == 2200.0
    assert r["by_type"] == {"Купе": 10, "Плац": 8}

def test_filter_car_type():
    r = api.match_seats(_train(), car_types=["Compartment"])
    assert r["total"] == 10
    assert r["by_type"] == {"Купе": 10}

def test_filter_berth_lower_main_only():
    r = api.match_seats(_train(), berth="lower")
    # "нижнее" = основные нижние (без боковых): Купе 6 + Плац 3
    assert r["total"] == 9
    assert r["by_type"] == {"Купе": 6, "Плац": 3}

def test_filter_berth_upper_main_only():
    r = api.match_seats(_train(), berth="upper")
    assert r["total"] == 7             # Купе 4 + Плац 3

def test_filter_berth_side():
    r = api.match_seats(_train(), berth="side")
    # боковые есть только в плаце (1+1); купе-группа без боковых отсекается
    assert r["total"] == 2
    assert r["by_type"] == {"Плац": 2}

def test_filter_berth_excludes_group_without_match():
    train = {"CarGroups": [
        {"AvailabilityIndication": "Available", "CarType": "Compartment", "CarTypeName": "Купе",
         "PlaceQuantity": 2, "LowerPlaceQuantity": 0, "UpperPlaceQuantity": 2, "MinPrice": 3000.0},
    ]}
    assert api.match_seats(train, berth="lower")["total"] == 0
    assert api.match_seats(train, berth="upper")["total"] == 2

def test_filter_berth_cabin():
    train = {"CarGroups": [
        {"AvailabilityIndication": "Available", "CarType": "Compartment", "CarTypeName": "Купе",
         "PlaceQuantity": 0, "TotalPlaceQuantity": 12, "LowerPlaceQuantity": 6,
         "UpperPlaceQuantity": 6, "EmptyCabinQuantity": 3, "MinPrice": 2062.4},
        {"AvailabilityIndication": "Available", "CarType": "ReservedSeat", "CarTypeName": "Плац",
         "PlaceQuantity": 5, "EmptyCabinQuantity": 0, "MinPrice": 1600.0},
    ]}
    r = api.match_seats(train, berth="cabin")
    assert r["total"] == 3             # 3 пустых купе; плац без пустых купе отсекается
    assert r["by_type"] == {"Купе": 3}

def test_filter_max_price():
    r = api.match_seats(_train(), max_price=3000)
    assert r["total"] == 8             # только Плац (2200 <= 3000)
    assert r["by_type"] == {"Плац": 8}

def test_total_place_quantity_used_over_place_quantity():
    # реальная форма РЖД (поезд 090Г): PlaceQuantity=0, но места есть в TotalPlaceQuantity
    train = {"CarGroups": [
        {"AvailabilityIndication": "Available", "CarType": "Compartment", "CarTypeName": "Купе",
         "PlaceQuantity": 0, "TotalPlaceQuantity": 12,
         "LowerPlaceQuantity": 6, "UpperPlaceQuantity": 6, "MinPrice": 2062.4},
    ]}
    assert api.match_seats(train)["total"] == 12
    assert api.count_available_seats(train) == 12
    # фильтр "купе нижнее" -> 6 нижних, а не "нет мест"
    assert api.match_seats(train, car_types=["Compartment"], berth="lower")["total"] == 6

def test_empty_train():
    r = api.match_seats({})
    assert r == {"total": 0, "lower": 0, "upper": 0, "side": 0, "min_price": None, "by_type": {}}
