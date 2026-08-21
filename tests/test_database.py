import os
import tempfile
import sqlite3
from database.manager import DatabaseManager
from database.models import Subscription
from datetime import datetime


def test_database_crud_tmpdb(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        # point config to temp DB
        monkeypatch.setenv("DATABASE_PATH", db_path)
        from importlib import reload
        import config as cfg
        reload(cfg)
        from database import manager as mgr
        reload(mgr)
        dm = mgr.DatabaseManager()

        sub = Subscription(
            id=None,
            user_id=123,
            origin_code="2000001",
            origin_name="Москва",
            destination_code="2000003",
            destination_name="Санкт-Петербург",
            departure_date="2025-01-15T00:00:00",
            train_numbers="",
            car_types="",
            min_seats=1,
            adult_passengers=1,
            children_passengers=0,
            interval_minutes=5,
            is_active=True,
            created_at=datetime.now(),
        )
        sub_id = dm.create_subscription(sub)
        assert isinstance(sub_id, int)
        subs = dm.get_user_subscriptions(123)
        assert len(subs) == 1
        assert subs[0].origin_name == "Москва"

        ok = dm.disable_subscription(sub_id, 123)
        assert ok is True


def _make_db(tmp, monkeypatch):
    """Свежий DatabaseManager на временной БД (по образцу test_database_crud_tmpdb)."""
    monkeypatch.setenv("DATABASE_PATH", os.path.join(tmp, "db.sqlite"))
    from importlib import reload
    import config as cfg
    reload(cfg)
    from database import manager as mgr
    reload(mgr)
    return mgr.DatabaseManager()


def _sub(**kw):
    base = dict(
        id=None, user_id=777, origin_code="2000000", origin_name="Москва",
        destination_code="2060000", destination_name="Ярославль",
        departure_date="2026-09-21T00:00:00", train_numbers="", car_types="",
        min_seats=1, adult_passengers=1, children_passengers=0, interval_minutes=5,
        is_active=True, created_at=datetime.now(),
    )
    base.update(kw)
    return Subscription(**base)


def test_include_disabled_defaults_to_false(monkeypatch):
    """Новая подписка по умолчанию скрывает места для инвалидов (#9)."""
    with tempfile.TemporaryDirectory() as tmp:
        dm = _make_db(tmp, monkeypatch)
        sid = dm.create_subscription(_sub())
        assert dm.get_subscription(sid, 777).include_disabled is False
        assert dm.get_user_subscriptions(777)[0].include_disabled is False


def test_update_subscription_filters_persists_include_disabled(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        dm = _make_db(tmp, monkeypatch)
        sid = dm.create_subscription(_sub())
        assert dm.update_subscription_filters(sid, 777, car_types='', berth='any',
                                              max_price=0, min_seats=1,
                                              include_disabled=True) is True
        assert dm.get_subscription(sid, 777).include_disabled is True


def test_migration_adds_include_disabled_to_old_db(monkeypatch):
    """Старая БД без колонки читается, подписка получает False."""
    with tempfile.TemporaryDirectory() as tmp:
        dm = _make_db(tmp, monkeypatch)
        sid = dm.create_subscription(_sub())
        conn = sqlite3.connect(dm.db_path)
        conn.execute("ALTER TABLE subscriptions DROP COLUMN include_disabled")
        conn.commit()
        conn.close()
        dm.init_database()  # повторная инициализация должна вернуть колонку
        assert dm.get_subscription(sid, 777).include_disabled is False
