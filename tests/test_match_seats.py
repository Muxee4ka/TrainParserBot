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
    assert r["lower"] == 10            # 6 + (3+1 боковой)
    assert r["upper"] == 8             # 4 + (3+1 боковой)
    assert r["min_price"] == 2200.0
    assert r["by_type"] == {"Купе": 10, "Плац": 8}

def test_filter_car_type():
    r = api.match_seats(_train(), car_types=["Compartment"])
    assert r["total"] == 10
    assert r["by_type"] == {"Купе": 10}

def test_filter_berth_lower():
    r = api.match_seats(_train(), berth="lower")
    # при фильтре "нижнее" total = число нижних мест (а не всех мест группы)
    assert r["total"] == 10            # Купе низ 6 + Плац низ (3+1 боковой)
    assert r["lower"] == 10
    assert r["by_type"] == {"Купе": 6, "Плац": 4}

def test_filter_berth_excludes_group_without_lower():
    # группа без нижних мест не попадает под фильтр "нижнее"
    train = {"CarGroups": [
        {"AvailabilityIndication": "Available", "CarType": "Compartment", "CarTypeName": "Купе",
         "PlaceQuantity": 2, "LowerPlaceQuantity": 0, "UpperPlaceQuantity": 2, "MinPrice": 3000.0},
    ]}
    assert api.match_seats(train, berth="lower")["total"] == 0
    assert api.match_seats(train, berth="upper")["total"] == 2

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
    # без фильтра считаем по TotalPlaceQuantity, а не по PlaceQuantity(=0)
    assert api.match_seats(train)["total"] == 12
    assert api.count_available_seats(train) == 12
    # фильтр "купе нижнее" -> 6 нижних, а не "нет мест"
    assert api.match_seats(train, car_types=["Compartment"], berth="lower")["total"] == 6

def test_empty_train():
    r = api.match_seats({})
    assert r == {"total": 0, "lower": 0, "upper": 0, "min_price": None, "by_type": {}}
