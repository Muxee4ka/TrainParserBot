# "N мест рядом" (сидячие вагоны) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a subscription filter that lets a user monitor sitting-car trains (`CarType == 'Sedentary'`, e.g. Ласточка) for "N seats free in one physical block" — exposed as a new `berth` value `'together'` plus an editable seat-count (reusing the existing, currently-unexposed `Subscription.min_seats` field).

**Architecture:** Generalize the existing `cabin`/`pair` seatmap-detail mechanism in `services/rzd_seatmap.py` (which already groups `CarPricing` free places by `CompartmentNumber`) into a threshold-based `blocks_with_at_least()`, add a `together_seats_detail()` wrapper scoped to `CarType == 'Sedentary'`, and thread a new `min_count` parameter through the existing `SEATMAP_BERTHS` call sites in `handlers/search.py` and `services/monitoring.py`. No new DB columns/migrations: `berth` is a free-text column (new string value `'together'`) and `min_seats` already exists in both `Subscription` and `SearchState` and is already persisted — this work just starts exposing/editing it via the filter panel.

**Tech Stack:** Python 3.10+, aiogram 3, sqlite3 (raw), pytest.

## Global Constraints

- No new database columns or migrations — `berth` (TEXT) accepts the new value `'together'` as-is; `min_seats` (INTEGER) is already a column on both `subscriptions` and `search_states`.
- Backward compatible: existing subscriptions with `berth` in `{any, lower, upper, side, cabin, pair}` and `min_seats=1` (default) must keep working exactly as before.
- `'together'` scope is `CarType == 'Sedentary'` only — do not touch `cabin`/`pair` semantics (Compartment/ReservedSeat).
- Known accepted approximation (from spec): "≥N free seats in one `CompartmentNumber` block" is treated as "N seats together", even though a block's free seats aren't guaranteed physically contiguous once partially sold.
- All new tests are unit tests (no `@pytest.mark.integration`), must stay green under plain `pytest`.
- Follow existing code style: Russian docstrings/comments/UI strings, `logger.error` + safe fallback on exceptions (no bare raises from service/handler methods).

---

### Task 1: `services/rzd_seatmap.py` — threshold-based block matching for Sedentary

**Files:**
- Modify: `services/rzd_seatmap.py`
- Test: `tests/test_seatmap.py`

**Interfaces:**
- Consumes: existing `parse_compartments(payload, car_types=None, max_price=0, include_types=(...))` (unchanged).
- Produces:
  - `blocks_with_at_least(payload: dict, min_size: int, car_types=None, max_price: int = 0, include_types=("Compartment",)) -> list[dict]` — each item `{"car": str, "compartment": str, "places": list[int]}`.
  - `together_seats_detail(payload: dict, min_count: int, car_types=None, max_price: int = 0) -> list[dict]` — same shape, `include_types=("Sedentary",)`.
  - `SEATMAP_BERTHS = ('cabin', 'pair', 'together')`.
  - `detail_for_berth(payload, berth, car_types=None, max_price=0, min_count=1) -> list` — routes `'together'` to `together_seats_detail`.
  - `format_seat_groups(detail: list, limit: int = 6) -> str`.
  - `format_seatmap_detail(berth, detail, limit=6)` — routes `'together'` to `format_seat_groups`.

- [ ] **Step 1: Write the failing tests**

Add to the top of `tests/test_seatmap.py`, replacing the existing import line:

```python
from services.rzd_seatmap import (
    count_empty_compartments, empty_compartments_detail, format_empty_cabins,
    pair_compartments_detail, detail_for_berth, format_pairs, SeatMapService,
    together_seats_detail, format_seat_groups, SEATMAP_BERTHS,
)
```

Append at the end of the file:

```python
def _payload_sedentary():
    # сидячий вагон (Ласточка): блоки переменного размера, без деления на низ/верх
    return {"Cars": [
        {"CarType": "Sedentary", "CarNumber": "06", "FreePlacesByCompartments": [
            {"CompartmentNumber": "1", "Places": "1, 2"},
            {"CompartmentNumber": "3", "Places": "5, 6, 8"},
            {"CompartmentNumber": "9", "Places": "35, 36, 38, 39, 40, 42"},
        ]},
        # плацкартный вагон не должен попадать в подсчёт сидячих групп
        {"CarType": "ReservedSeat", "CarNumber": "10", "FreePlacesByCompartments": [
            {"CompartmentNumber": "1", "Places": "1, 2, 3, 4"},
        ]},
    ]}


def test_seatmap_berths_includes_together():
    assert SEATMAP_BERTHS == ('cabin', 'pair', 'together')


def test_together_seats_detail_threshold():
    detail = together_seats_detail(_payload_sedentary(), 3)
    # блок 1 (2 места) не проходит порог; блок 3 (3) и блок 9 (6) проходят
    assert [d["compartment"] for d in detail] == ["3", "9"]


def test_together_seats_detail_ignores_other_car_types():
    detail = together_seats_detail(_payload_sedentary(), 4)
    assert all(d["car"] == "06" for d in detail)  # плацкартный вагон 10 не попал


def test_together_seats_detail_default_min_count_one():
    detail = together_seats_detail(_payload_sedentary(), 1)
    assert len(detail) == 3  # все три блока сидячего вагона


def test_detail_for_berth_together_routes():
    assert detail_for_berth(_payload_sedentary(), "together", min_count=3) == \
           together_seats_detail(_payload_sedentary(), 3)


def test_detail_for_berth_together_default_min_count():
    assert detail_for_berth(_payload_sedentary(), "together") == \
           together_seats_detail(_payload_sedentary(), 1)


def test_format_seat_groups():
    detail = together_seats_detail(_payload_sedentary(), 3)
    assert format_seat_groups(detail) == (
        "вагон 06: блок 3 (3 мест: 5, 6, 8); вагон 06: блок 9 (6 мест: 35, 36, 38, 39, 40, 42)"
    )


def test_format_seatmap_detail_together():
    from services.rzd_seatmap import format_seatmap_detail
    detail = together_seats_detail(_payload_sedentary(), 3)
    assert format_seatmap_detail("together", detail) == format_seat_groups(detail)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_seatmap.py -v`
Expected: `ImportError`/`ModuleNotFoundError`-style collection failure — `together_seats_detail`, `format_seat_groups`, `SEATMAP_BERTHS` (with 3 values) don't exist yet.

- [ ] **Step 3: Implement**

In `services/rzd_seatmap.py`, change:

```python
# Фильтры полки, требующие схему вагона (сетевой запрос)
SEATMAP_BERTHS = ('cabin', 'pair')
```

to:

```python
# Фильтры полки, требующие схему вагона (сетевой запрос)
SEATMAP_BERTHS = ('cabin', 'pair', 'together')
```

Replace the existing `empty_compartments_detail` function:

```python
def empty_compartments_detail(payload: dict, car_types=None, max_price: int = 0) -> list:
    """Полностью свободные купе: [{'car','compartment','places':[...]}], отсортировано.
    Только купейные вагоны (целиком пустое купе — понятие купе)."""
    result = []
    comps_by_car = parse_compartments(payload, car_types=car_types, max_price=max_price,
                                      include_types=("Compartment",))
    for number, comps in comps_by_car.items():
        for comp, cell in comps.items():
            if len(cell["all"]) >= COMPARTMENT_SIZE:
                result.append({"car": number, "compartment": comp, "places": sorted(cell["all"])})
    result.sort(key=_sort_key)
    return result
```

with:

```python
def blocks_with_at_least(payload: dict, min_size: int, car_types=None, max_price: int = 0,
                         include_types=("Compartment",)) -> list:
    """Блоки (вагон+CompartmentNumber), где свободно >= min_size мест:
    [{'car','compartment','places':[...]}], отсортировано."""
    result = []
    comps_by_car = parse_compartments(payload, car_types=car_types, max_price=max_price,
                                      include_types=include_types)
    for number, comps in comps_by_car.items():
        for comp, cell in comps.items():
            if len(cell["all"]) >= min_size:
                result.append({"car": number, "compartment": comp, "places": sorted(cell["all"])})
    result.sort(key=_sort_key)
    return result


def empty_compartments_detail(payload: dict, car_types=None, max_price: int = 0) -> list:
    """Полностью свободные купе: [{'car','compartment','places':[...]}], отсортировано.
    Только купейные вагоны (целиком пустое купе — понятие купе)."""
    return blocks_with_at_least(payload, COMPARTMENT_SIZE, car_types=car_types, max_price=max_price,
                                include_types=("Compartment",))


def together_seats_detail(payload: dict, min_count: int, car_types=None, max_price: int = 0) -> list:
    """Блоки сидячих мест (Sedentary), где свободно >= min_count мест рядом (одна
    физическая группа кресел по CompartmentNumber). Приближение: если внутри блока
    часть мест продана, оставшиеся свободные необязательно физически смежны."""
    return blocks_with_at_least(payload, max(1, min_count), car_types=car_types, max_price=max_price,
                                include_types=("Sedentary",))
```

Replace the existing `detail_for_berth` function:

```python
def detail_for_berth(payload: dict, berth: str, car_types=None, max_price: int = 0) -> list:
    """Детали под нужный фильтр полки ('cabin' | 'pair') с учётом категорий и цены."""
    if berth == "pair":
        return pair_compartments_detail(payload, car_types=car_types, max_price=max_price)
    return empty_compartments_detail(payload, car_types=car_types, max_price=max_price)
```

with:

```python
def detail_for_berth(payload: dict, berth: str, car_types=None, max_price: int = 0,
                     min_count: int = 1) -> list:
    """Детали под нужный фильтр полки ('cabin' | 'pair' | 'together') с учётом категорий
    и цены. min_count используется только веткой 'together' (сколько мест нужно рядом)."""
    if berth == "pair":
        return pair_compartments_detail(payload, car_types=car_types, max_price=max_price)
    if berth == "together":
        return together_seats_detail(payload, min_count, car_types=car_types, max_price=max_price)
    return empty_compartments_detail(payload, car_types=car_types, max_price=max_price)
```

After `format_pairs`, add:

```python
def format_seat_groups(detail: list, limit: int = 6) -> str:
    """Список групп сидячих мест: 'вагон 06: блок 3 (3 мест: 5, 6, 8)'."""
    parts = []
    for d in detail[:limit]:
        places = ", ".join(map(str, d["places"]))
        parts.append(f"вагон {d['car']}: блок {d['compartment']} ({len(d['places'])} мест: {places})")
    tail = f"; и ещё {len(detail) - limit}" if len(detail) > limit else ""
    return "; ".join(parts) + tail
```

Replace `format_seatmap_detail`:

```python
def format_seatmap_detail(berth: str, detail: list, limit: int = 6) -> str:
    """Человекочитаемый список под фильтр полки."""
    return format_pairs(detail, limit) if berth == "pair" else format_empty_cabins(detail, limit)
```

with:

```python
def format_seatmap_detail(berth: str, detail: list, limit: int = 6) -> str:
    """Человекочитаемый список под фильтр полки."""
    if berth == "pair":
        return format_pairs(detail, limit)
    if berth == "together":
        return format_seat_groups(detail, limit)
    return format_empty_cabins(detail, limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_seatmap.py -v`
Expected: all tests PASS (existing `cabin`/`pair` tests must still pass unchanged).

- [ ] **Step 5: Commit**

```bash
git add services/rzd_seatmap.py tests/test_seatmap.py
git commit -m "feat: add together_seats_detail for Sedentary seat blocks"
```

---

### Task 2: `SeatMapService` — plumb `min_count` through the network-calling wrapper

**Files:**
- Modify: `services/rzd_seatmap.py`
- Test: `tests/test_seatmap.py`

**Interfaces:**
- Consumes: `detail_for_berth`/`SEATMAP_BERTHS` from Task 1.
- Produces:
  - `SeatMapService.detail_for_berth(self, berth, origin_code, destination_code, departure_datetime, train_number, provider="P1", car_types=None, max_price=0, min_count=1)`.
  - `SeatMapService.count_for_berth(self, berth, origin_code, destination_code, departure_datetime, train_number, provider="P1", car_types=None, max_price=0, min_count=1)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_seatmap.py`:

```python
def test_seatmap_service_together_min_count(monkeypatch):
    svc = SeatMapService()
    monkeypatch.setattr(svc, "_fetch", lambda *a, **k: _payload_sedentary())
    n = svc.count_for_berth("together", "2064150", "2064130", "2026-07-07T16:10:00", "812С",
                            min_count=3)
    assert n == 2  # блоки 3 и 9 (>= 3 места)


def test_seatmap_service_together_default_min_count(monkeypatch):
    svc = SeatMapService()
    monkeypatch.setattr(svc, "_fetch", lambda *a, **k: _payload_sedentary())
    n = svc.count_for_berth("together", "2064150", "2064130", "2026-07-07T16:10:00", "812С")
    assert n == 3  # min_count по умолчанию 1 -> все три блока


def test_seatmap_service_cabin_unaffected_by_min_count(monkeypatch):
    svc = SeatMapService()
    monkeypatch.setattr(svc, "_fetch", lambda *a, **k: _payload_typed())
    # min_count не используется для 'cabin' — поведение не меняется
    n = svc.count_for_berth("cabin", "A", "B", "2026-07-01T00:00:00", "001A", min_count=5)
    assert n == svc.count_for_berth("cabin", "A", "B", "2026-07-01T00:00:00", "001A")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_seatmap.py -v -k seatmap_service_together`
Expected: `TypeError: count_for_berth() got an unexpected keyword argument 'min_count'`.

- [ ] **Step 3: Implement**

Replace the two `SeatMapService` methods:

```python
    def detail_for_berth(self, berth: str, origin_code: str, destination_code: str,
                         departure_datetime: str, train_number: str, provider: str = "P1",
                         car_types=None, max_price: int = 0):
        """Детали под фильтр полки ('cabin'|'pair') с учётом категорий/цены, или None при ошибке."""
        try:
            payload = self._fetch(origin_code, destination_code, departure_datetime, train_number, provider)
            return detail_for_berth(payload, berth, car_types=car_types, max_price=max_price)
        except Exception as e:
            logger.error(f"Схема вагонов недоступна ({train_number}): {e}")
            return None

    def count_for_berth(self, berth: str, origin_code: str, destination_code: str,
                        departure_datetime: str, train_number: str, provider: str = "P1",
                        car_types=None, max_price: int = 0):
        """Число подходящих купе под фильтр полки или None при сетевой ошибке."""
        detail = self.detail_for_berth(
            berth, origin_code, destination_code, departure_datetime, train_number, provider,
            car_types=car_types, max_price=max_price,
        )
        return None if detail is None else len(detail)
```

with:

```python
    def detail_for_berth(self, berth: str, origin_code: str, destination_code: str,
                         departure_datetime: str, train_number: str, provider: str = "P1",
                         car_types=None, max_price: int = 0, min_count: int = 1):
        """Детали под фильтр полки ('cabin'|'pair'|'together') с учётом категорий/цены,
        или None при ошибке. min_count используется только веткой 'together'."""
        try:
            payload = self._fetch(origin_code, destination_code, departure_datetime, train_number, provider)
            return detail_for_berth(payload, berth, car_types=car_types, max_price=max_price,
                                    min_count=min_count)
        except Exception as e:
            logger.error(f"Схема вагонов недоступна ({train_number}): {e}")
            return None

    def count_for_berth(self, berth: str, origin_code: str, destination_code: str,
                        departure_datetime: str, train_number: str, provider: str = "P1",
                        car_types=None, max_price: int = 0, min_count: int = 1):
        """Число подходящих купе/групп под фильтр полки или None при сетевой ошибке."""
        detail = self.detail_for_berth(
            berth, origin_code, destination_code, departure_datetime, train_number, provider,
            car_types=car_types, max_price=max_price, min_count=min_count,
        )
        return None if detail is None else len(detail)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_seatmap.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/rzd_seatmap.py tests/test_seatmap.py
git commit -m "feat: plumb min_count through SeatMapService for together filter"
```

---

### Task 3: `services/filters.py` — panel context, button, summary, keyboard

**Files:**
- Modify: `services/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Produces:
  - `build_filter_context(cargroups)` — adds `"show_seat_group": bool` key.
  - `format_filter_summary(car_types, berth, max_price, min_seats=1) -> str`.
  - `build_filter_keyboard(car_types, berth, max_price, context, submit_text=..., submit_cb=..., min_seats=1) -> list`.
  - `matched_unit("together") == "групп мест"` (via existing `_BERTH_UNIT` dict, unchanged function).

- [ ] **Step 1: Write the failing tests**

In `tests/test_filters.py`, replace the existing `test_seated_keyboard_has_classes_no_berths` test (its assumption changes: seated trains now show `'any'`/`'together'`, just not `lower`/`upper`/`side`/`cabin`/`pair`):

```python
def test_seated_keyboard_has_classes_no_berths():
```

becomes:

```python
def test_seated_keyboard_has_classes_and_together_no_lower_upper():
    ctx = f.build_filter_context(_seated_cargroups())
    kb = f.build_filter_keyboard("", "any", 0, ctx, min_seats=3)
    cbs = [b["callback_data"] for row in kb for b in row]
    assert "flt_car_Эконом+" in cbs
    assert "flt_berth_lower" not in cbs and "flt_berth_upper" not in cbs  # полок нет у сидячих
    assert "flt_berth_together" in cbs
    assert "flt_seats_set" in cbs
    assert "flt_price_set" in cbs  # ввод цены вручную
```

Append new tests at the end of the file:

```python
def test_build_filter_context_seated_train_shows_seat_group():
    ctx = f.build_filter_context(_seated_cargroups())
    assert ctx["show_seat_group"] is True


def test_build_filter_context_berth_train_no_seat_group():
    ctx = f.build_filter_context(_berth_cargroups())
    assert ctx["show_seat_group"] is False


def test_berth_keyboard_no_together_for_berth_train():
    ctx = f.build_filter_context(_berth_cargroups())
    kb = f.build_filter_keyboard("", "any", 0, ctx)
    cbs = [b["callback_data"] for row in kb for b in row]
    assert "flt_berth_together" not in cbs
    assert "flt_seats_set" not in cbs


def test_seats_button_shows_current_count():
    ctx = f.build_filter_context(_seated_cargroups())
    kb = f.build_filter_keyboard("", "together", 0, ctx, min_seats=3)
    flat = [b for row in kb for b in row]
    seats_btn = next(b for b in flat if b["callback_data"] == "flt_seats_set")
    assert "3" in seats_btn["text"]


def test_format_filter_summary_together():
    assert f.format_filter_summary("", "together", 0, min_seats=3) == "3+ мест рядом"
    assert f.format_filter_summary("", "together", 5000, min_seats=2) == "2+ мест рядом · до 5000 ₽"


def test_matched_unit_together():
    assert f.matched_unit("together") == "групп мест"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_filters.py -v`
Expected: multiple FAILs — `show_seat_group` KeyError, `flt_berth_together`/`flt_seats_set` not found, `format_filter_summary` doesn't accept `min_seats`, `matched_unit("together")` returns `"мест"` not `"групп мест"`.

- [ ] **Step 3: Implement**

Replace:

```python
_BERTH_SUMMARY = {"lower": "нижнее", "upper": "верхнее", "side": "боковое",
                  "cabin": "купе целиком", "pair": "низ+верх в одном купе"}
_BERTH_BTN = {"any": "Любая", "lower": "Нижнее", "upper": "Верхнее", "side": "Боковое",
              "cabin": "🚪 Купе целиком", "pair": "🔼🔽 Низ+Верх вместе"}
_BERTH_UNIT = {"cabin": "пустых купе", "pair": "купе с парой низ+верх"}
```

with:

```python
_BERTH_SUMMARY = {"lower": "нижнее", "upper": "верхнее", "side": "боковое",
                  "cabin": "купе целиком", "pair": "низ+верх в одном купе"}
_BERTH_BTN = {"any": "Любая", "lower": "Нижнее", "upper": "Верхнее", "side": "Боковое",
              "cabin": "🚪 Купе целиком", "pair": "🔼🔽 Низ+Верх вместе",
              "together": "🔗 Мест рядом"}
_BERTH_UNIT = {"cabin": "пустых купе", "pair": "купе с парой низ+верх", "together": "групп мест"}
```

Replace `build_filter_context`:

```python
def build_filter_context(cargroups: list) -> dict:
    """Контекст фильтров из вагонов поезда: какие категории и ряды показывать, диапазон цен."""
    avail = [cg for cg in (cargroups or []) if cg.get("AvailabilityIndication") == "Available"]
    categories = []
    seen = set()
    prices = []
    has_compartment = has_reserved = False
    for cg in avail:
        ct = cg.get("CarType")
        if ct == "Compartment":
            has_compartment = True
        elif ct == "ReservedSeat":
            has_reserved = True
        tok = category_token(cg)
        if tok not in seen:
            seen.add(tok)
            categories.append({"value": tok, "label": category_label(cg)})
        for k in ("MinPrice", "MaxPrice"):
            if cg.get(k):
                prices.append(cg[k])
    return {
        "categories": categories,
        "has_berths": has_compartment or has_reserved,
        "show_side": has_reserved,
        "show_cabin_pair": has_compartment,
        "price_min": int(min(prices)) if prices else 0,
        "price_max": int(max(prices)) if prices else 0,
    }
```

with:

```python
def build_filter_context(cargroups: list) -> dict:
    """Контекст фильтров из вагонов поезда: какие категории и ряды показывать, диапазон цен."""
    avail = [cg for cg in (cargroups or []) if cg.get("AvailabilityIndication") == "Available"]
    categories = []
    seen = set()
    prices = []
    has_compartment = has_reserved = has_sedentary = False
    for cg in avail:
        ct = cg.get("CarType")
        if ct == "Compartment":
            has_compartment = True
        elif ct == "ReservedSeat":
            has_reserved = True
        elif ct == "Sedentary":
            has_sedentary = True
        tok = category_token(cg)
        if tok not in seen:
            seen.add(tok)
            categories.append({"value": tok, "label": category_label(cg)})
        for k in ("MinPrice", "MaxPrice"):
            if cg.get(k):
                prices.append(cg[k])
    return {
        "categories": categories,
        "has_berths": has_compartment or has_reserved,
        "show_side": has_reserved,
        "show_cabin_pair": has_compartment,
        "show_seat_group": has_sedentary,
        "price_min": int(min(prices)) if prices else 0,
        "price_max": int(max(prices)) if prices else 0,
    }
```

Replace `format_filter_summary`:

```python
def format_filter_summary(car_types: str, berth: str, max_price: int) -> str:
    """Человекочитаемая сводка фильтра."""
    parts = []
    codes = [c for c in (car_types or "").split(",") if c]
    if codes:
        parts.append(", ".join(CAR_TYPE_LABELS.get(c, c) for c in codes))
    if berth in _BERTH_SUMMARY:
        parts.append(_BERTH_SUMMARY[berth])
    if max_price:
        parts.append(f"до {max_price} ₽")
    return " · ".join(parts) if parts else "любые места"
```

with:

```python
def format_filter_summary(car_types: str, berth: str, max_price: int, min_seats: int = 1) -> str:
    """Человекочитаемая сводка фильтра."""
    parts = []
    codes = [c for c in (car_types or "").split(",") if c]
    if codes:
        parts.append(", ".join(CAR_TYPE_LABELS.get(c, c) for c in codes))
    if berth == "together":
        parts.append(f"{max(1, min_seats)}+ мест рядом")
    elif berth in _BERTH_SUMMARY:
        parts.append(_BERTH_SUMMARY[berth])
    if max_price:
        parts.append(f"до {max_price} ₽")
    return " · ".join(parts) if parts else "любые места"
```

Replace `_berth_options`:

```python
def _berth_options(context: dict) -> list:
    """Доступные варианты полки под тип поезда."""
    opts = ["any", "lower", "upper"]
    if context.get("show_side"):
        opts.append("side")
    if context.get("show_cabin_pair"):
        opts += ["cabin", "pair"]
    return opts
```

with:

```python
def _berth_options(context: dict) -> list:
    """Доступные варианты полки под тип поезда."""
    opts = ["any"]
    if context.get("has_berths"):
        opts += ["lower", "upper"]
        if context.get("show_side"):
            opts.append("side")
        if context.get("show_cabin_pair"):
            opts += ["cabin", "pair"]
    if context.get("show_seat_group"):
        opts.append("together")
    return opts
```

Replace `build_filter_keyboard`:

```python
def build_filter_keyboard(car_types: str, berth: str, max_price: int, context: dict,
                          submit_text: str = "🔔 Подписаться",
                          submit_cb: str = "subscribe_filtered") -> list:
    """Inline-клавиатура фильтров, адаптированная под поезд (context)."""
    selected = set(c for c in (car_types or "").split(",") if c)
    rows = []

    # Категории вагонов/классов — по 2 в ряд
    cats = context.get("categories", [])
    for i in range(0, len(cats), 2):
        rows.append([_btn(c["label"], f"flt_car_{c['value']}", c["value"] in selected)
                     for c in cats[i:i + 2]])

    # Полка — только если есть купе/плац, по одной кнопке в ряд
    if context.get("has_berths"):
        for val in _berth_options(context):
            rows.append([_btn(_BERTH_BTN[val], f"flt_berth_{val}", berth == val)])

    # Цена — ввод суммы вручную (кнопка открывает запрос ввода)
    if context.get("price_max"):
        cap = f"≤ {max_price} ₽" if max_price else "любая"
        price_row = [{"text": f"💰 Цена: {cap} (изменить)", "callback_data": "flt_price_set"}]
        if max_price:
            price_row.append({"text": "♾ Сброс", "callback_data": "flt_price_0"})
        rows.append(price_row)

    rows.append([{"text": submit_text, "callback_data": submit_cb, "style": "primary"}])
    return rows
```

with:

```python
def build_filter_keyboard(car_types: str, berth: str, max_price: int, context: dict,
                          submit_text: str = "🔔 Подписаться",
                          submit_cb: str = "subscribe_filtered",
                          min_seats: int = 1) -> list:
    """Inline-клавиатура фильтров, адаптированная под поезд (context)."""
    selected = set(c for c in (car_types or "").split(",") if c)
    rows = []

    # Категории вагонов/классов — по 2 в ряд
    cats = context.get("categories", [])
    for i in range(0, len(cats), 2):
        rows.append([_btn(c["label"], f"flt_car_{c['value']}", c["value"] in selected)
                     for c in cats[i:i + 2]])

    # Полка — если есть купе/плац, или «мест рядом» для сидячих; по одной кнопке в ряд
    if context.get("has_berths") or context.get("show_seat_group"):
        for val in _berth_options(context):
            rows.append([_btn(_BERTH_BTN[val], f"flt_berth_{val}", berth == val)])

    # Количество мест рядом — только когда доступен фильтр "вместе" (сидячие вагоны)
    if context.get("show_seat_group"):
        rows.append([{"text": f"🔢 Мест: {max(1, min_seats)} (изменить)",
                      "callback_data": "flt_seats_set"}])

    # Цена — ввод суммы вручную (кнопка открывает запрос ввода)
    if context.get("price_max"):
        cap = f"≤ {max_price} ₽" if max_price else "любая"
        price_row = [{"text": f"💰 Цена: {cap} (изменить)", "callback_data": "flt_price_set"}]
        if max_price:
            price_row.append({"text": "♾ Сброс", "callback_data": "flt_price_0"})
        rows.append(price_row)

    rows.append([{"text": submit_text, "callback_data": submit_cb, "style": "primary"}])
    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_filters.py -v`
Expected: all tests PASS, including the updated `test_seated_keyboard_has_classes_and_together_no_lower_upper` and all pre-existing `_berth_cargroups()`-based tests (unchanged order/values for non-Sedentary trains).

- [ ] **Step 5: Commit**

```bash
git add services/filters.py tests/test_filters.py
git commit -m "feat: add 'together' berth option and seat-count control to filter panel"
```

---

### Task 4: `database/manager.py` — `update_subscription_filters` gains `min_seats`

**Files:**
- Modify: `database/manager.py`
- Test: `tests/test_filters_db.py`

**Interfaces:**
- Produces: `DatabaseManager.update_subscription_filters(self, subscription_id, user_id, car_types, berth, max_price, min_seats) -> bool` (new required parameter, no default — every call site must pass it explicitly).

- [ ] **Step 1: Write the failing tests**

In `tests/test_filters_db.py`, replace:

```python
def test_update_subscription_filters():
    from database import Subscription
    from datetime import datetime
    db = _fresh_db()
    sub = Subscription(id=None, user_id=1, origin_code="A", origin_name="A",
                       destination_code="B", destination_name="B",
                       departure_date="2026-07-01T00:00:00", train_numbers="",
                       car_types="", min_seats=1, adult_passengers=1, children_passengers=0,
                       interval_minutes=5, is_active=True, created_at=datetime.now())
    sid = db.create_subscription(sub)
    ok = db.update_subscription_filters(sid, 1, "Compartment", "cabin", 8000)
    assert ok is True
    got = db.get_subscription(sid, 1)
    assert got.car_types == "Compartment" and got.berth == "cabin" and got.max_price == 8000
    # чужой пользователь не может изменить
    assert db.update_subscription_filters(sid, 999, "Soft", "lower", 0) is False
```

with:

```python
def test_update_subscription_filters():
    from database import Subscription
    from datetime import datetime
    db = _fresh_db()
    sub = Subscription(id=None, user_id=1, origin_code="A", origin_name="A",
                       destination_code="B", destination_name="B",
                       departure_date="2026-07-01T00:00:00", train_numbers="",
                       car_types="", min_seats=1, adult_passengers=1, children_passengers=0,
                       interval_minutes=5, is_active=True, created_at=datetime.now())
    sid = db.create_subscription(sub)
    ok = db.update_subscription_filters(sid, 1, "Compartment", "cabin", 8000, 1)
    assert ok is True
    got = db.get_subscription(sid, 1)
    assert got.car_types == "Compartment" and got.berth == "cabin" and got.max_price == 8000
    # чужой пользователь не может изменить
    assert db.update_subscription_filters(sid, 999, "Soft", "lower", 0, 1) is False


def test_update_subscription_filters_min_seats_together():
    from database import Subscription
    from datetime import datetime
    db = _fresh_db()
    sub = Subscription(id=None, user_id=1, origin_code="A", origin_name="A",
                       destination_code="B", destination_name="B",
                       departure_date="2026-07-01T00:00:00", train_numbers="",
                       car_types="", min_seats=1, adult_passengers=1, children_passengers=0,
                       interval_minutes=5, is_active=True, created_at=datetime.now())
    sid = db.create_subscription(sub)
    ok = db.update_subscription_filters(sid, 1, "Sedentary", "together", 0, 3)
    assert ok is True
    got = db.get_subscription(sid, 1)
    assert got.berth == "together" and got.min_seats == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_filters_db.py -v`
Expected: `TypeError: update_subscription_filters() takes 6 positional arguments but 7 were given` (for the new test) and the modified `test_update_subscription_filters` fails the same way.

- [ ] **Step 3: Implement**

In `database/manager.py`, replace:

```python
    def update_subscription_filters(self, subscription_id: int, user_id: int,
                                    car_types: str, berth: str, max_price: int) -> bool:
        """Обновление фильтров (тип вагона / полка / цена) существующей подписки"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE subscriptions
                SET car_types = ?, berth = ?, max_price = ?
                WHERE id = ? AND user_id = ?
            ''', (car_types, berth, max_price, subscription_id, user_id))
            success = cursor.rowcount > 0
            conn.commit()
            if success:
                logger.info(f"Фильтры подписки #{subscription_id} обновлены")
            return success
        except Exception as e:
            logger.error(f"Ошибка обновления фильтров подписки: {e}")
            return False
        finally:
            conn.close()
```

with:

```python
    def update_subscription_filters(self, subscription_id: int, user_id: int,
                                    car_types: str, berth: str, max_price: int,
                                    min_seats: int) -> bool:
        """Обновление фильтров (тип вагона / полка / цена / кол-во мест) существующей подписки"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE subscriptions
                SET car_types = ?, berth = ?, max_price = ?, min_seats = ?
                WHERE id = ? AND user_id = ?
            ''', (car_types, berth, max_price, min_seats, subscription_id, user_id))
            success = cursor.rowcount > 0
            conn.commit()
            if success:
                logger.info(f"Фильтры подписки #{subscription_id} обновлены")
            return success
        except Exception as e:
            logger.error(f"Ошибка обновления фильтров подписки: {e}")
            return False
        finally:
            conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_filters_db.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add database/manager.py tests/test_filters_db.py
git commit -m "feat: persist min_seats when updating subscription filters"
```

---

### Task 5: `handlers/search.py` — filter panel UX wiring

**Files:**
- Modify: `handlers/search.py`

**Interfaces:**
- Consumes: `SEATMAP_BERTHS`, `detail_for_berth`/`count_for_berth(..., min_count=...)` (Tasks 1-2); `format_filter_summary(..., min_seats=...)`, `build_filter_keyboard(..., min_seats=...)` (Task 3); `DatabaseManager.update_subscription_filters(..., min_seats)` (Task 4).
- Produces: `SearchHandler.handle_seats_input(self, message, search_state)` — new method; `search_step == 'await_seats'` as a recognized state.

No dedicated unit tests for this task: `handlers/search.py` methods take live aiogram `Message`/`CallbackQuery` objects and the existing test suite doesn't unit-test this file beyond `_panel_text` (already covered, untouched here). Correctness for this task is verified by Task 7's full-suite run (which exercises every function this task calls) plus the manual review in Step 3.

- [ ] **Step 1: Locate and understand call sites**

Run: `grep -n "SEATMAP_BERTHS\|format_filter_summary\|filter_berth =\|await_price\|update_subscription_filters" handlers/search.py`

Confirm the following methods still match the snippets below before editing (line numbers may have shifted slightly from prior commits, but the surrounding code should be unchanged): `handle_text_message`, `handle_select_train`, `_render_filter_panel`, `handle_filter_toggle`, `handle_price_input`, `handle_edit_filters`, `save_subscription_filters`, `subscribe_to_selected_train`, `check_subscription_now`.

- [ ] **Step 2: Wire the new `await_seats` step into the text-message dispatcher**

Replace:

```python
            elif search_state.search_step == 'await_price':
                await self.handle_price_input(message, search_state)
            else:
```

with:

```python
            elif search_state.search_step == 'await_price':
                await self.handle_price_input(message, search_state)
            elif search_state.search_step == 'await_seats':
                await self.handle_seats_input(message, search_state)
            else:
```

- [ ] **Step 3: Reset `min_seats` when a fresh train is selected**

Replace, inside `handle_select_train`:

```python
            search_state.selected_train_number = train_number
            search_state.selected_train_info = train_info
            search_state.search_step = 'done'
            search_state.selected_train_cargroups = self._store_train(selected or {})
            search_state.filter_car_types = ''
            search_state.filter_berth = 'any'
            search_state.filter_max_price = 0
            search_state.editing_subscription_id = None
```

with:

```python
            search_state.selected_train_number = train_number
            search_state.selected_train_info = train_info
            search_state.search_step = 'done'
            search_state.selected_train_cargroups = self._store_train(selected or {})
            search_state.filter_car_types = ''
            search_state.filter_berth = 'any'
            search_state.filter_max_price = 0
            search_state.min_seats = 1
            search_state.editing_subscription_id = None
```

- [ ] **Step 4: Pass `min_count`/`min_seats` through `_render_filter_panel`**

Replace:

```python
        from services.rzd_seatmap import SeatMapService, SEATMAP_BERTHS
        if search_state.filter_berth in SEATMAP_BERTHS:
            # точный подсчёт купе через схему вагонов (сетевой запрос — в поток)
            n = await asyncio.to_thread(
                SeatMapService().count_for_berth, search_state.filter_berth,
                search_state.origin_code, search_state.destination_code, dep,
                search_state.selected_train_number, provider,
                car_types or None, search_state.filter_max_price,
            )
            matched = {'total': n if n is not None else 0}
        else:
            matched = self.rzd_api.match_seats(
                train, car_types=car_types or None,
                berth=search_state.filter_berth, max_price=search_state.filter_max_price,
            )
        summary = flt.format_filter_summary(
            search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price
        )
```

with:

```python
        from services.rzd_seatmap import SeatMapService, SEATMAP_BERTHS
        if search_state.filter_berth in SEATMAP_BERTHS:
            # точный подсчёт купе через схему вагонов (сетевой запрос — в поток)
            n = await asyncio.to_thread(
                SeatMapService().count_for_berth, search_state.filter_berth,
                search_state.origin_code, search_state.destination_code, dep,
                search_state.selected_train_number, provider,
                car_types or None, search_state.filter_max_price,
                min_count=search_state.min_seats,
            )
            matched = {'total': n if n is not None else 0}
        else:
            matched = self.rzd_api.match_seats(
                train, car_types=car_types or None,
                berth=search_state.filter_berth, max_price=search_state.filter_max_price,
            )
        summary = flt.format_filter_summary(
            search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price,
            search_state.min_seats,
        )
```

A few lines below in the same method, replace:

```python
        context = flt.build_filter_context(cargroups)
        keyboard = flt.build_filter_keyboard(
            search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price,
            context, submit_text=submit_text, submit_cb=submit_cb,
        )
```

with:

```python
        context = flt.build_filter_context(cargroups)
        keyboard = flt.build_filter_keyboard(
            search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price,
            context, submit_text=submit_text, submit_cb=submit_cb, min_seats=search_state.min_seats,
        )
```

- [ ] **Step 5: Handle the `flt_seats_set` callback and add `handle_seats_input`**

Replace, inside `handle_filter_toggle`:

```python
            kind, value = parsed
            if kind == 'car':
                search_state.filter_car_types = flt.toggle_car_type(search_state.filter_car_types, value)
            elif kind == 'berth':
                search_state.filter_berth = value
            elif kind == 'price':
                if value == 'set':
                    # запрашиваем сумму вводом сообщением
                    search_state.search_step = 'await_price'
                    self.db_manager.save_search_state(search_state)
                    sent_id = await self.notification_service.send_message(
                        user_id,
                        "💰 Введите максимальную цену в рублях (например 8000).\nОтправьте 0 — без лимита.",
                    )
                    if sent_id:
                        search_state.messages_to_delete.append(sent_id)
                        self.db_manager.save_search_state(search_state)
                    await callback.answer("Введите цену сообщением")
                    return
                # value == '0' — сброс лимита
                search_state.filter_max_price = 0
            self.db_manager.save_search_state(search_state)
```

with:

```python
            kind, value = parsed
            if kind == 'car':
                search_state.filter_car_types = flt.toggle_car_type(search_state.filter_car_types, value)
            elif kind == 'berth':
                search_state.filter_berth = value
            elif kind == 'price':
                if value == 'set':
                    # запрашиваем сумму вводом сообщением
                    search_state.search_step = 'await_price'
                    self.db_manager.save_search_state(search_state)
                    sent_id = await self.notification_service.send_message(
                        user_id,
                        "💰 Введите максимальную цену в рублях (например 8000).\nОтправьте 0 — без лимита.",
                    )
                    if sent_id:
                        search_state.messages_to_delete.append(sent_id)
                        self.db_manager.save_search_state(search_state)
                    await callback.answer("Введите цену сообщением")
                    return
                # value == '0' — сброс лимита
                search_state.filter_max_price = 0
            elif kind == 'seats' and value == 'set':
                # запрашиваем количество мест вводом сообщением
                search_state.search_step = 'await_seats'
                self.db_manager.save_search_state(search_state)
                sent_id = await self.notification_service.send_message(
                    user_id,
                    "🔢 Введите нужное количество мест (например 3).",
                )
                if sent_id:
                    search_state.messages_to_delete.append(sent_id)
                    self.db_manager.save_search_state(search_state)
                await callback.answer("Введите количество мест сообщением")
                return
            self.db_manager.save_search_state(search_state)
```

Then, right after `handle_price_input` (before `handle_edit_filters`), insert a new method:

```python
    async def handle_seats_input(self, message: Message, search_state: SearchState):
        """Обработка ручного ввода количества мест (после кнопки «Мест: N»)."""
        try:
            digits = ''.join(ch for ch in (message.text or '') if ch.isdigit())
            search_state.min_seats = max(1, int(digits)) if digits else 1
            # возвращаемся к панели фильтров
            search_state.search_step = 'done'
            self.db_manager.save_search_state(search_state)
            await self._render_filter_panel(message.chat.id, search_state)
            await self._delete_user_messages(message.chat.id, search_state)
        except Exception as e:
            logger.error(f"Ошибка ввода количества мест: {e}")
            search_state.search_step = 'done'
            self.db_manager.save_search_state(search_state)
```

- [ ] **Step 6: Carry `min_seats` into edit/save flows**

Replace, inside `handle_edit_filters`:

```python
            search_state.filter_car_types = sub.car_types or ''
            search_state.filter_berth = sub.berth or 'any'
            search_state.filter_max_price = sub.max_price or 0
            search_state.editing_subscription_id = subscription_id
```

with:

```python
            search_state.filter_car_types = sub.car_types or ''
            search_state.filter_berth = sub.berth or 'any'
            search_state.filter_max_price = sub.max_price or 0
            search_state.min_seats = sub.min_seats or 1
            search_state.editing_subscription_id = subscription_id
```

Replace, inside `save_subscription_filters`:

```python
            sub_id = search_state.editing_subscription_id
            ok = self.db_manager.update_subscription_filters(
                sub_id, user_id,
                search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price,
            )
            summary = flt.format_filter_summary(
                search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price
            )
```

with:

```python
            sub_id = search_state.editing_subscription_id
            ok = self.db_manager.update_subscription_filters(
                sub_id, user_id,
                search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price,
                search_state.min_seats,
            )
            summary = flt.format_filter_summary(
                search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price,
                search_state.min_seats,
            )
```

- [ ] **Step 7: Update the new-subscription confirmation text**

Replace, inside `subscribe_to_selected_train`:

```python
                    f"Фильтр: {flt.format_filter_summary(search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price)}\n\n"
```

with:

```python
                    f"Фильтр: {flt.format_filter_summary(search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price, search_state.min_seats)}\n\n"
```

- [ ] **Step 8: Pass `min_count`/`min_seats` in "Проверить сейчас"**

Replace, inside `check_subscription_now`:

```python
                if berth in seatmap_berths:
                    # точный список купе через схему вагонов (сетевой запрос — в поток)
                    detail = await asyncio.to_thread(
                        SeatMapService().detail_for_berth, berth,
                        subscription.origin_code, subscription.destination_code,
                        train.get('LocalDepartureDateTime'),
                        train.get('TrainNumber') or train.get('DisplayTrainNumber') or '',
                        train.get('Provider', 'P1'),
                        car_types or None, max_price,
                    )
```

with:

```python
                if berth in seatmap_berths:
                    # точный список купе через схему вагонов (сетевой запрос — в поток)
                    detail = await asyncio.to_thread(
                        SeatMapService().detail_for_berth, berth,
                        subscription.origin_code, subscription.destination_code,
                        train.get('LocalDepartureDateTime'),
                        train.get('TrainNumber') or train.get('DisplayTrainNumber') or '',
                        train.get('Provider', 'P1'),
                        car_types or None, max_price,
                        min_count=subscription.min_seats,
                    )
```

A few lines below, in the same method, replace:

```python
            summary = flt.format_filter_summary(subscription.car_types, berth, max_price)
```

with:

```python
            summary = flt.format_filter_summary(subscription.car_types, berth, max_price, subscription.min_seats)
```

- [ ] **Step 9: Sanity-check the file imports and compiles**

Run: `python -c "import ast; ast.parse(open('handlers/search.py').read())"`
Expected: no output (no `SyntaxError`).

Run: `pytest -m "not integration" -q`
Expected: all PASS (this exercises the updated `filters.py`/`rzd_seatmap.py`/`database/manager.py` call signatures used by this file, catching any signature mismatch through import-time or existing-test failures).

- [ ] **Step 10: Commit**

```bash
git add handlers/search.py
git commit -m "feat: wire 'together' seats filter into the subscription filter panel"
```

---

### Task 6: `services/monitoring.py` + `handlers/commands.py` — monitoring loop and `/subscriptions` wiring

**Files:**
- Modify: `services/monitoring.py`
- Modify: `handlers/commands.py`
- Test: `tests/test_monitoring_filters.py`

**Interfaces:**
- Consumes: `SeatMapService.count_for_berth(..., min_count=...)` (Task 2), `format_filter_summary(..., min_seats=...)` (Task 3).
- Produces: `MonitoringService.count_matched` and `MonitoringService.format_availability_message` now forward `subscription.min_seats` as `min_count` whenever `subscription.berth in SEATMAP_BERTHS`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_monitoring_filters.py`:

```python
def test_count_matched_together_passes_min_seats(monkeypatch):
    from services import rzd_seatmap
    captured = {}

    def fake_count_for_berth(self, berth, *args, **kwargs):
        captured['min_count'] = kwargs.get('min_count')
        return 2

    monkeypatch.setattr(rzd_seatmap.SeatMapService, "count_for_berth", fake_count_for_berth)
    api = RZDAPIService()
    sub = _sub(berth="together", min_seats=3, car_types="Sedentary")
    train = {"TrainNumber": "812С", "CarGroups": [], "LocalDepartureDateTime": "2026-07-07T16:10:00"}
    n = MonitoringService.count_matched(api, sub, train)
    assert n == 2
    assert captured['min_count'] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_monitoring_filters.py -v -k together`
Expected: FAIL — `captured['min_count']` is `None` (current code never passes `min_count`), or `AssertionError: assert None == 3`.

- [ ] **Step 3: Implement**

In `services/monitoring.py`, replace `count_matched`:

```python
    @staticmethod
    def count_matched(rzd_api, subscription, train) -> int:
        """Сколько мест поезда подходит под фильтр подписки.

        Для berth 'cabin'/'pair' считает купе через схему вагонов (CarPricing) —
        агрегатных данных недостаточно. Иначе — match_seats.
        """
        from services.rzd_seatmap import SeatMapService, SEATMAP_BERTHS
        if subscription.berth in SEATMAP_BERTHS:
            car_types = [c for c in (subscription.car_types or '').split(',') if c]
            n = SeatMapService().count_for_berth(
                subscription.berth,
                subscription.origin_code, subscription.destination_code,
                train.get('LocalDepartureDateTime'),
                train.get('TrainNumber') or train.get('DisplayTrainNumber') or '',
                train.get('Provider', 'P1'),
                car_types=car_types or None, max_price=subscription.max_price,
            )
            return n or 0
        car_types = [c for c in (subscription.car_types or '').split(',') if c]
        return rzd_api.match_seats(
            train, car_types=car_types or None,
            berth=subscription.berth, max_price=subscription.max_price,
        )['total']
```

with:

```python
    @staticmethod
    def count_matched(rzd_api, subscription, train) -> int:
        """Сколько мест поезда подходит под фильтр подписки.

        Для berth 'cabin'/'pair'/'together' считает через схему вагонов (CarPricing) —
        агрегатных данных недостаточно. Иначе — match_seats.
        """
        from services.rzd_seatmap import SeatMapService, SEATMAP_BERTHS
        if subscription.berth in SEATMAP_BERTHS:
            car_types = [c for c in (subscription.car_types or '').split(',') if c]
            n = SeatMapService().count_for_berth(
                subscription.berth,
                subscription.origin_code, subscription.destination_code,
                train.get('LocalDepartureDateTime'),
                train.get('TrainNumber') or train.get('DisplayTrainNumber') or '',
                train.get('Provider', 'P1'),
                car_types=car_types or None, max_price=subscription.max_price,
                min_count=subscription.min_seats,
            )
            return n or 0
        car_types = [c for c in (subscription.car_types or '').split(',') if c]
        return rzd_api.match_seats(
            train, car_types=car_types or None,
            berth=subscription.berth, max_price=subscription.max_price,
        )['total']
```

Replace, in `format_availability_message`:

```python
        summary = format_filter_summary(subscription.car_types, berth, max_price)
        message += f"Фильтр: {summary}\n\n"
```

with:

```python
        summary = format_filter_summary(subscription.car_types, berth, max_price, subscription.min_seats)
        message += f"Фильтр: {summary}\n\n"
```

Further down in the same method, replace:

```python
            if berth in SEATMAP_BERTHS:
                # точный список купе через схему вагонов (с номерами)
                detail = SeatMapService().detail_for_berth(
                    berth,
                    subscription.origin_code, subscription.destination_code,
                    train.get('LocalDepartureDateTime'),
                    train.get('TrainNumber') or train.get('DisplayTrainNumber') or '',
                    train.get('Provider', 'P1'),
                    car_types=car_types or None, max_price=max_price,
                ) or []
```

with:

```python
            if berth in SEATMAP_BERTHS:
                # точный список купе через схему вагонов (с номерами)
                detail = SeatMapService().detail_for_berth(
                    berth,
                    subscription.origin_code, subscription.destination_code,
                    train.get('LocalDepartureDateTime'),
                    train.get('TrainNumber') or train.get('DisplayTrainNumber') or '',
                    train.get('Provider', 'P1'),
                    car_types=car_types or None, max_price=max_price,
                    min_count=subscription.min_seats,
                ) or []
```

In `handlers/commands.py`, replace:

```python
                filter_summary = format_filter_summary(
                    subscription.car_types, subscription.berth, subscription.max_price
                )
```

with:

```python
                filter_summary = format_filter_summary(
                    subscription.car_types, subscription.berth, subscription.max_price,
                    subscription.min_seats,
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_monitoring_filters.py -v`
Expected: all tests PASS, including the new `test_count_matched_together_passes_min_seats`.

- [ ] **Step 5: Commit**

```bash
git add services/monitoring.py handlers/commands.py tests/test_monitoring_filters.py
git commit -m "feat: forward min_seats to seatmap calls in monitoring and /subscriptions"
```

---

### Task 7: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the complete unit test suite**

Run: `pytest -m "not integration" -q`
Expected: all tests PASS, zero failures/errors. This includes every test added in Tasks 1-6 plus the full pre-existing suite (`test_api.py` integration-marked tests are skipped; everything else must be green).

- [ ] **Step 2: Confirm no accidental scope creep**

Run: `git status --short` and `git diff --stat master`
Expected: only the files listed in Tasks 1-6 (`services/rzd_seatmap.py`, `services/filters.py`, `database/manager.py`, `handlers/search.py`, `services/monitoring.py`, `handlers/commands.py`, and the corresponding test files) plus this plan/spec's own commits are touched.

- [ ] **Step 3: Manual read-through checklist**

Confirm, by reading the diff (`git diff master`):
- No new DB columns/migrations were introduced (per Global Constraints).
- `berth == 'together'` is the only new enum value; `cabin`/`pair`/`lower`/`upper`/`side`/`any` behavior is untouched.
- Every call site of `format_filter_summary`, `build_filter_keyboard`, `SeatMapService.count_for_berth`/`detail_for_berth`, and `update_subscription_filters` in the whole repo was updated (re-run `grep -rn "format_filter_summary\|build_filter_keyboard\|update_subscription_filters" --include=*.py .` and check every non-test hit was touched by Tasks 3-6).

No commit for this task — it's a verification gate. If Step 1 or 2 finds a problem, fix it in the relevant task's file and re-run.
