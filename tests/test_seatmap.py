from services.rzd_seatmap import parse_window_counts, SeatMapService


def test_parse_window_counts_known_shape():
    payload = {"Cars": [{"Places": [
        {"Number": 1, "IsAvailable": True, "Window": True},
        {"Number": 2, "IsAvailable": True, "Window": False},
        {"Number": 3, "IsAvailable": False, "Window": True},
    ]}]}
    assert parse_window_counts(payload) == {"window": 1, "other": 1}


def test_parse_window_counts_unknown_shape_returns_none():
    assert parse_window_counts({"foo": "bar"}) is None
    assert parse_window_counts({}) is None


def test_get_window_counts_graceful_on_error(monkeypatch):
    svc = SeatMapService()

    def boom(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(svc, "_fetch", boom)
    assert svc.get_window_counts("001A", "Compartment", "A", "B", "2026-07-01T00:00:00") is None
