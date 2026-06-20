import os, tempfile, importlib

def _fresh_db():
    import config
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd); os.unlink(path)
    config.config.DATABASE_PATH = path
    from database import manager as m
    importlib.reload(m)
    return m.DatabaseManager()

def test_subscription_roundtrip_with_filters():
    from database import Subscription
    from datetime import datetime
    db = _fresh_db()
    sub = Subscription(id=None, user_id=1, origin_code="2000000", origin_name="A",
                       destination_code="2004000", destination_name="B",
                       departure_date="2026-07-01T00:00:00", train_numbers="",
                       car_types="Compartment,ReservedSeat", min_seats=1,
                       adult_passengers=1, children_passengers=0, interval_minutes=5,
                       is_active=True, created_at=datetime.now(),
                       berth="lower", max_price=8000)
    sid = db.create_subscription(sub)
    got = db.get_subscription(sid, 1)
    assert got.berth == "lower" and got.max_price == 8000
    assert got.car_types == "Compartment,ReservedSeat"

def test_search_state_roundtrip_with_filters():
    from database import SearchState
    db = _fresh_db()
    st = SearchState(user_id=5, filter_car_types="Sedentary", filter_berth="upper",
                     filter_max_price=5000, selected_train_cargroups='[{"x":1}]')
    db.save_search_state(st)
    got = db.get_search_state(5)
    assert got.filter_car_types == "Sedentary" and got.filter_berth == "upper"
    assert got.filter_max_price == 5000 and got.selected_train_cargroups == '[{"x":1}]'

def test_migration_idempotent():
    db = _fresh_db()
    db.init_database()  # повторный вызов не падает
    db.init_database()
