"""Места для инвалидов исключаются из подсчётов и минимальной цены (#9).

РЖД отдаёт такие места отдельной CarGroup целиком (проверено на 8 поездах,
см. docs/superpowers/specs/2026-08-21-disabled-seats-and-seat-detail-design.md),
поэтому достаточно отбросить группу по флагу HasPlacesForDisabledPersons.
"""
from services.rzd_api import RZDAPIService


def _group(disabled=False, available=True, price=1000, total=4, **kw):
    """Группа вагонов с полями, которые читают match_seats / breakdown / min_price."""
    g = {
        'AvailabilityIndication': 'Available' if available else 'NotAvailable',
        'HasPlacesForDisabledPersons': disabled,
        'MinPrice': price,
        'TotalPlaceQuantity': total,
        'LowerPlaceQuantity': total,
        'UpperPlaceQuantity': 0,
        'LowerSidePlaceQuantity': 0,
        'UpperSidePlaceQuantity': 0,
        'EmptyCabinQuantity': 0,
        'CarType': 'Compartment',
        'CarTypeName': 'КУПЕ',
    }
    g.update(kw)
    return g


def test_group_allowed_skips_disabled_by_default():
    api = RZDAPIService()
    assert api._group_allowed(_group(disabled=False)) is True
    assert api._group_allowed(_group(disabled=True)) is False


def test_group_allowed_honours_include_disabled():
    api = RZDAPIService()
    assert api._group_allowed(_group(disabled=True), include_disabled=True) is True


def test_group_allowed_still_skips_unavailable():
    api = RZDAPIService()
    assert api._group_allowed(_group(available=False)) is False
    assert api._group_allowed(_group(available=False), include_disabled=True) is False


def test_min_price_ignores_cheaper_disabled_group():
    """Реальный случай: поезд 711М, инвалидное место 1014.1 против обычного 2093.2."""
    api = RZDAPIService()
    train = {'CarGroups': [_group(price=2093.2), _group(disabled=True, price=1014.1)]}
    assert api.min_price(train) == 2093.2
    assert api.min_price(train, include_disabled=True) == 1014.1


def test_match_seats_excludes_disabled_group():
    api = RZDAPIService()
    train = {'CarGroups': [
        _group(price=2093.2, total=4),
        _group(disabled=True, price=1014.1, total=2),
    ]}
    assert api.match_seats(train)['total'] == 4
    assert api.match_seats(train)['min_price'] == 2093.2
    assert api.match_seats(train, include_disabled=True)['total'] == 6
    assert api.match_seats(train, include_disabled=True)['min_price'] == 1014.1


def test_count_seats_breakdown_excludes_disabled_group():
    api = RZDAPIService()
    train = {'CarGroups': [_group(total=4), _group(disabled=True, total=2)]}
    assert api.count_seats_breakdown(train)['total'] == 4
    assert api.count_seats_breakdown(train, include_disabled=True)['total'] == 6


def test_missing_flag_is_treated_as_not_disabled():
    """Старые/урезанные ответы без поля не должны молча терять места."""
    api = RZDAPIService()
    g = _group()
    del g['HasPlacesForDisabledPersons']
    assert api._group_allowed(g) is True
    assert api.min_price({'CarGroups': [g]}) == 1000
