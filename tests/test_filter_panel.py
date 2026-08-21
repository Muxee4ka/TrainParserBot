from handlers.search import SearchHandler


def test_panel_text():
    sh = SearchHandler.__new__(SearchHandler)  # без __init__/роутера
    breakdown = {"total": 14, "by_type": {"Купе": 6, "Плац": 8}, "lower": 9, "upper": 5, "min_price": 2200.0}
    matched = {"total": 6}
    txt = sh._panel_text(breakdown, matched, "Купе · нижнее")
    assert "Найдено мест: 14" in txt
    assert "Купе 6" in txt and "Плац 8" in txt
    assert "низ 9 / верх 5" in txt
    assert "от 2200" in txt
    assert "Под фильтр" in txt and "6" in txt
    assert "Купе · нижнее" in txt


# ── Тумблер мест для инвалидов (#9) ──────────────────────────────────────────

def test_summary_mentions_disabled_only_when_shown():
    """В типовом случае (скрыты) сводку не засоряем."""
    from services.filters import format_filter_summary
    assert "инвалид" not in format_filter_summary("", "any", 0, 1).lower()
    assert "инвалид" not in format_filter_summary("", "any", 0, 1,
                                                  include_disabled=False).lower()
    assert "инвалид" in format_filter_summary("", "any", 0, 1,
                                              include_disabled=True).lower()


def test_panel_has_disabled_toggle():
    from services.filters import build_filter_keyboard
    rows = build_filter_keyboard("", "any", 0, {"categories": []}, include_disabled=False)
    data = [b["callback_data"] for row in rows for b in row]
    assert "flt_disabled_1" in data  # выключено → кнопка предлагает включить


def test_panel_toggle_flips_when_enabled():
    from services.filters import build_filter_keyboard
    rows = build_filter_keyboard("", "any", 0, {"categories": []}, include_disabled=True)
    data = [b["callback_data"] for row in rows for b in row]
    assert "flt_disabled_0" in data


def test_disabled_callback_parses():
    from services.filters import parse_filter_callback
    assert parse_filter_callback("flt_disabled_1") == ("disabled", "1")
    assert parse_filter_callback("flt_disabled_0") == ("disabled", "0")


def test_disabled_callback_within_length_limit():
    from config import config
    assert len("flt_disabled_1") <= config.MAX_CALLBACK_DATA_LENGTH


def test_search_state_round_trips_include_disabled(monkeypatch):
    """Тумблер переживает сохранение состояния панели (#9)."""
    import os, tempfile
    from importlib import reload
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("DATABASE_PATH", os.path.join(tmp, "db.sqlite"))
        import config as cfg
        reload(cfg)
        from database import manager as mgr
        reload(mgr)
        from database.models import SearchState
        dm = mgr.DatabaseManager()

        st = SearchState(user_id=42)
        assert st.filter_include_disabled is False
        st.filter_include_disabled = True
        dm.save_search_state(st)
        assert dm.get_search_state(42).filter_include_disabled is True

        st.filter_include_disabled = False
        dm.save_search_state(st)
        assert dm.get_search_state(42).filter_include_disabled is False
