from services.rzd_seatmap import (
    count_empty_compartments, empty_compartments_detail, format_empty_cabins,
    pair_compartments_detail, detail_for_berth, format_pairs, SeatMapService,
)


def _payload_typed():
    # вагон разбит на строки по типу полки (CarPlaceNameRu), как реальный CarPricing
    return {"Cars": [
        {"CarType": "Compartment", "CarNumber": "27", "CarPlaceNameRu": "Нижнее",
         "FreePlacesByCompartments": [
             {"CompartmentNumber": "1", "Places": "1, 3"},   # купе 1: только низ
             {"CompartmentNumber": "2", "Places": "5"},       # купе 2: низ
         ]},
        {"CarType": "Compartment", "CarNumber": "27", "CarPlaceNameRu": "Верхнее",
         "FreePlacesByCompartments": [
             {"CompartmentNumber": "2", "Places": "6, 8"},    # купе 2: верх -> пара!
             {"CompartmentNumber": "3", "Places": "10, 12"},  # купе 3: только верх
         ]},
    ]}


def test_pair_compartments_detail():
    detail = pair_compartments_detail(_payload_typed())
    # пара низ+верх только в купе 2
    assert len(detail) == 1
    d = detail[0]
    assert d["car"] == "27" and d["compartment"] == "2"
    assert d["lower"] == [5] and d["upper"] == [6, 8]


def test_detail_for_berth_routes():
    assert detail_for_berth(_payload_typed(), "pair") == pair_compartments_detail(_payload_typed())
    assert detail_for_berth(_payload_typed(), "cabin") == empty_compartments_detail(_payload_typed())


def test_format_pairs():
    detail = pair_compartments_detail(_payload_typed())
    assert format_pairs(detail) == "вагон 27: купе 2 (низ 5, верх 6, 8)"


def _payload_mixed():
    # купейный вагон 14 и плацкартный вагон 01 (как в issue #4: фильтр Плац не должен брать купе)
    return {"Cars": [
        {"CarType": "Compartment", "CarNumber": "14", "CarPlaceNameRu": "Нижнее",
         "FreePlacesByCompartments": [{"CompartmentNumber": "1", "Places": "1, 3"}]},
        {"CarType": "Compartment", "CarNumber": "14", "CarPlaceNameRu": "Верхнее",
         "FreePlacesByCompartments": [{"CompartmentNumber": "1", "Places": "2, 4"}]},
        {"CarType": "ReservedSeat", "CarNumber": "01", "CarPlaceNameRu": "Нижнее",
         "FreePlacesByCompartments": [{"CompartmentNumber": "5", "Places": "17"}]},
        {"CarType": "ReservedSeat", "CarNumber": "01", "CarPlaceNameRu": "Верхнее",
         "FreePlacesByCompartments": [{"CompartmentNumber": "5", "Places": "18, 20"}]},
    ]}


def test_pair_respects_car_types_plac_only():
    # фильтр «Плац» (ReservedSeat) -> пары только в плацкарте, купе 14 игнор
    detail = pair_compartments_detail(_payload_mixed(), car_types=["ReservedSeat"])
    assert [d["car"] for d in detail] == ["01"]


def test_pair_respects_car_types_kupe_only():
    detail = pair_compartments_detail(_payload_mixed(), car_types=["Compartment"])
    assert [d["car"] for d in detail] == ["14"]


def test_cabin_only_compartment_even_without_filter():
    # пустые купе считаются только в купейных вагонах, плац не попадает
    detail = empty_compartments_detail(_payload_mixed())
    assert all(d["car"] == "14" for d in detail)


def _payload():
    # реальная форма CarPricing: один вагон 27 разбит на строки (разные тарифы),
    # места внутри купе надо объединять. Купе 1/3/4 — полные (4 места), 2 — нет.
    return {"Cars": [
        {"CarType": "Compartment", "CarNumber": "27", "FreePlacesByCompartments": [
            {"CompartmentNumber": "2", "Places": "6, 8"},
            {"CompartmentNumber": "3", "Places": "10, 12"},
            {"CompartmentNumber": "4", "Places": "14, 16"},
        ]},
        {"CarType": "Compartment", "CarNumber": "27", "FreePlacesByCompartments": [
            {"CompartmentNumber": "1", "Places": "2, 4"},
            {"CompartmentNumber": "3", "Places": "9, 11"},
            {"CompartmentNumber": "4", "Places": "13, 15"},
        ]},
        {"CarType": "Compartment", "CarNumber": "27", "FreePlacesByCompartments": [
            {"CompartmentNumber": "1", "Places": "1, 3"},
        ]},
        # плацкартный вагон игнорируется
        {"CarType": "ReservedSeat", "CarNumber": "10", "FreePlacesByCompartments": [
            {"CompartmentNumber": "1", "Places": "1, 2, 3, 4"},
        ]},
    ]}


def test_count_empty_compartments_merges_rows():
    # купе 1 (1,2,3,4), 3 (9,10,11,12), 4 (13,14,15,16) — полные; 2 (6,8) — нет
    assert count_empty_compartments(_payload()) == 3


def test_empty_compartments_detail_has_place_numbers():
    detail = empty_compartments_detail(_payload())
    assert [d["compartment"] for d in detail] == ["1", "3", "4"]  # отсортировано
    comp3 = next(d for d in detail if d["compartment"] == "3")
    assert comp3["car"] == "27" and comp3["places"] == [9, 10, 11, 12]


def test_format_empty_cabins():
    detail = empty_compartments_detail(_payload())
    assert format_empty_cabins(detail) == "вагон 27: купе 1, 3, 4"
    assert format_empty_cabins([], ) == ""


def test_count_empty_compartments_empty_payload():
    assert count_empty_compartments({}) == 0
    assert count_empty_compartments({"Cars": []}) == 0


def test_count_empty_compartments_ignores_partial():
    payload = {"Cars": [
        {"CarType": "Compartment", "CarNumber": "5", "FreePlacesByCompartments": [
            {"CompartmentNumber": "1", "Places": "1, 2, 3"},  # 3 места — не полное
        ]},
    ]}
    assert count_empty_compartments(payload) == 0


def test_empty_compartments_graceful_on_error(monkeypatch):
    svc = SeatMapService()

    def boom(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(svc, "_fetch", boom)
    assert svc.empty_compartments("2060001", "2060440", "2026-06-22T16:10:00", "090Г") is None
