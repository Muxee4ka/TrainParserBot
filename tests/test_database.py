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
