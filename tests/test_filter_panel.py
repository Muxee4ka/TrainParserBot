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
