from services.rzd_seatmap import count_empty_compartments, SeatMapService


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
