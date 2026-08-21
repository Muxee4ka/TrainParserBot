# Инвалидные места (#9) + детальные уведомления (#8) Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. Execute task-by-task, running the stated command after each step.

**Goal:** (#9) Exclude disabled-persons seats from every count and price by default, with a per-subscription opt-out. (#8) Put car number, seat number, berth type and price into availability notifications for *all* filters, not just `cabin`/`pair`/`together`.

**Architecture:** #9 turns out to need no `CarPricing` at all — РЖД returns disabled seats as a whole dedicated `CarGroup` (verified 8/8 trains, see spec), so a single predicate `RZDAPIService._group_allowed()` shared by `count_seats_breakdown` / `match_seats` / `min_price` covers it at zero network cost. #8 introduces the real seam: a `TrainSeats` value object holding one parsed `CarPricing` payload, with all querying/formatting pure on top of it, and `SeatMapService.seats()` as the single network method. This also removes an existing double-`_fetch` on the notification path.

**Spec:** `docs/superpowers/specs/2026-08-21-disabled-seats-and-seat-detail-design.md`

**Tech Stack:** Python 3.10+, aiogram 3, sqlite3 (raw), pytest.

## Global Constraints

- Русские докстринги, комментарии и строки UI — как в остальном коде.
- Сервисные методы не пробрасывают исключения наружу: `logger.error` + безопасный фолбэк (`None` / пустой список), как сейчас.
- Дефолт `include_disabled=False` во всех новых сигнатурах — существующие вызовы в `handlers/search.py` и `services/monitoring.py` не правятся, кроме двух мест, где есть объект подписки.
- Строка состояния `_filtered_state` не меняет формат — иначе после деплоя все подписки дадут ложное уведомление.
- Новые тесты — юнит, без сети, зелёные под обычным `pytest`. Один интеграционный за `RUN_INTEGRATION_TESTS=1` на инвариант «помеченная группа целиком инвалидная».
- Миграция БД — ad-hoc `ALTER TABLE ... ADD COLUMN` в `DatabaseManager.init_database()`, как для остальных колонок. Без фреймворка миграций.
- `main.py` не трогаем — отдельный легаси-артефакт.

---

### Task 1: `services/rzd_api.py` — предикат `_group_allowed`

**Files:**
- Modify: `services/rzd_api.py:137` (`_available_count` рядом), `:212`, `:229`, `:287`
- Test: `tests/test_disabled_seats.py` (create)

**Interfaces:**
- Produces: `RZDAPIService._group_allowed(cg: Dict, include_disabled: bool = False) -> bool`; параметр `include_disabled: bool = False` на `count_seats_breakdown`, `match_seats`, `min_price`.

- [ ] **Step 1: Написать падающие тесты**

```python
import pytest
from services.rzd_api import RZDAPIService

def _group(disabled=False, available=True, price=1000, total=4, **kw):
    g = {
        'AvailabilityIndication': 'Available' if available else 'NotAvailable',
        'HasPlacesForDisabledPersons': disabled,
        'MinPrice': price,
        'TotalPlaceQuantity': total,
        'FreeSeats': total,
        'LowerPlaceQuantity': total,
        'UpperPlaceQuantity': 0,
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
    api = RZDAPIService()
    train = {'CarGroups': [_group(price=2093.2), _group(disabled=True, price=1014.1)]}
    assert api.min_price(train) == 2093.2
    assert api.min_price(train, include_disabled=True) == 1014.1

def test_match_seats_excludes_disabled_group():
    api = RZDAPIService()
    train = {'CarGroups': [_group(price=2093.2, total=4), _group(disabled=True, price=1014.1, total=2)]}
    assert api.match_seats(train)['total'] == 4
    assert api.match_seats(train)['min_price'] == 2093.2
    assert api.match_seats(train, include_disabled=True)['total'] == 6

def test_count_seats_breakdown_excludes_disabled_group():
    api = RZDAPIService()
    train = {'CarGroups': [_group(total=4), _group(disabled=True, total=2)]}
    assert api.count_seats_breakdown(train)['total'] == 4
    assert api.count_seats_breakdown(train, include_disabled=True)['total'] == 6
```

- [ ] **Step 2: Прогнать, убедиться что падают**

Run: `pytest tests/test_disabled_seats.py -v`
Expected: FAIL — `AttributeError: 'RZDAPIService' object has no attribute '_group_allowed'`, затем `TypeError: min_price() got an unexpected keyword argument`.

- [ ] **Step 3: Реализовать**

```python
    @staticmethod
    def _group_allowed(car_group: Dict, include_disabled: bool = False) -> bool:
        """Учитывать ли группу вагонов при подсчёте мест и цены.

        Места для инвалидов РЖД отдаёт отдельной группой целиком (проверено на
        8 поездах, см. спеку 2026-08-21), поэтому достаточно отбросить группу по
        флагу — обычные места при этом не теряются. Купить такое место в обычном
        сценарии нельзя, а стоит оно дешевле и портит минимальную цену поезда.
        """
        if car_group.get('AvailabilityIndication') != 'Available':
            return False
        if include_disabled:
            return True
        return not car_group.get('HasPlacesForDisabledPersons')
```

В трёх функциях заменить `if cg.get('AvailabilityIndication') != 'Available': continue` на `if not self._group_allowed(cg, include_disabled): continue` и добавить параметр в сигнатуру:

- `count_seats_breakdown(self, train: Dict, include_disabled: bool = False)`
- `match_seats(self, train, car_types=None, berth='any', max_price=0, include_disabled=False)`
- `min_price(self, train: Dict, include_disabled: bool = False)`

В `min_price` списковое включение переписать через предикат.

- [ ] **Step 4: Прогнать тесты**

Run: `pytest tests/test_disabled_seats.py -v && pytest -q`
Expected: новые PASS, вся существующая пачка зелёная.

- [ ] **Step 5: Коммит**

```bash
git add services/rzd_api.py tests/test_disabled_seats.py
git commit -m "feat: исключать места для инвалидов из подсчётов и минимальной цены (#9)"
```

---

### Task 2: БД — колонка `include_disabled`

**Files:**
- Modify: `database/models.py` (`Subscription`), `database/manager.py` (миграция, `create_subscription`, `_row_to_subscription`, `update_subscription_filters`)
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: ничего из Task 1.
- Produces: `Subscription.include_disabled: bool = False`; колонка `subscriptions.include_disabled INTEGER DEFAULT 0`; параметр `include_disabled` в `update_subscription_filters`.

- [ ] **Step 1: Тест на миграцию и круговорот**

```python
def test_subscription_include_disabled_defaults_false(tmp_path):
    db = DatabaseManager(str(tmp_path / "t.db"))
    sid = db.create_subscription(1, '2000000', 'Москва', '2060000', 'Ярославль', '2026-09-21')
    assert db.get_subscription(sid).include_disabled is False

def test_update_subscription_filters_persists_include_disabled(tmp_path):
    db = DatabaseManager(str(tmp_path / "t.db"))
    sid = db.create_subscription(1, '2000000', 'Москва', '2060000', 'Ярославль', '2026-09-21')
    db.update_subscription_filters(sid, car_types='', berth='any', max_price=0,
                                   min_seats=1, include_disabled=True)
    assert db.get_subscription(sid).include_disabled is True
```

- [ ] **Step 2: Прогнать, убедиться что падают**

Run: `pytest tests/test_database.py -k include_disabled -v`
Expected: FAIL — `AttributeError: 'Subscription' object has no attribute 'include_disabled'`.

- [ ] **Step 3: Реализовать**

Поле в `database/models.py`:

```python
    include_disabled: bool = False   # показывать места для инвалидов (по умолчанию скрыты)
```

Миграция в `init_database()` рядом с остальными `ALTER TABLE`:

```python
        self._add_column_if_missing(cursor, 'subscriptions', 'include_disabled', 'INTEGER DEFAULT 0')
```

(если приватного хелпера нет — повторить существующий inline-паттерн `try: cursor.execute("ALTER TABLE ...") except sqlite3.OperationalError: pass`).

В сборке `Subscription` из строки — `include_disabled=bool(row['include_disabled'])`. В `update_subscription_filters` добавить параметр `include_disabled: bool = False` и колонку в `UPDATE`.

- [ ] **Step 4: Прогнать тесты**

Run: `pytest tests/test_database.py -v && pytest -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add database/ tests/test_database.py
git commit -m "feat: колонка include_disabled у подписки (#9)"
```

---

### Task 3: Панель фильтров — тумблер инвалидных мест

**Files:**
- Modify: `services/filters.py` (контекст панели, кнопка, `format_filter_summary`), `handlers/search.py` (callback `flt_disabled_`)
- Test: `tests/test_filter_panel.py`

**Interfaces:**
- Consumes: `Subscription.include_disabled` из Task 2.
- Produces: callback-данные `flt_disabled_0` / `flt_disabled_1`; строка сводки «Места для инвалидов: показаны».

- [ ] **Step 1: Тесты**

```python
def test_summary_mentions_disabled_only_when_shown():
    assert 'инвалид' not in format_filter_summary('', 'any', 0, 1, include_disabled=False).lower()
    assert 'инвалид' in format_filter_summary('', 'any', 0, 1, include_disabled=True).lower()

def test_panel_has_disabled_toggle():
    kb = build_filter_keyboard(cargroups=[], car_types=[], berth='any', max_price=0,
                               min_seats=1, include_disabled=False, submit='subscribe_filtered')
    data = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert 'flt_disabled_1' in data
```

(точные имена функций/сигнатуры взять из текущего `services/filters.py` — тесты подогнать под них, не наоборот)

- [ ] **Step 2: Прогнать, убедиться что падают**

Run: `pytest tests/test_filter_panel.py -k disabled -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'include_disabled'`.

- [ ] **Step 3: Реализовать**

Кнопка по образцу существующих тумблеров, текст `♿ Инвалидные: скрыты` / `♿ Инвалидные: показаны`. В `format_filter_summary` строку добавлять только при `include_disabled=True`. В `handlers/search.py` — ветка `elif callback.data.startswith('flt_disabled_')` в `handle_callback`, пишет значение в `SearchState` и перерисовывает панель через `_render_filter_panel`.

Проверить лимит `MAX_CALLBACK_DATA_LENGTH=64` — `flt_disabled_1` укладывается.

- [ ] **Step 4: Прогнать тесты**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add services/filters.py handlers/search.py tests/test_filter_panel.py
git commit -m "feat: тумблер инвалидных мест в панели фильтров (#9)"
```

---

### Task 4: `services/rzd_seatmap.py` — `TrainSeats` и `SeatMapService.seats()`

**Files:**
- Modify: `services/rzd_seatmap.py:205` (`SeatMapService`)
- Test: `tests/test_seatmap_detail.py` (create)

**Interfaces:**
- Consumes: существующие чистые функции `parse_compartments`, `detail_for_berth`, `_berth_kind`.
- Produces:
  - `TrainSeats(payload: dict)` — чистый, без сети;
  - `TrainSeats.by_berth(berth, car_types=None, max_price=0, min_count=1, include_disabled=False) -> list`
  - `TrainSeats.count(...) -> int`
  - `TrainSeats.describe(berth, ..., limit=6) -> str`
  - `SeatMapService.seats(origin_code, destination_code, departure_datetime, train_number, provider='P1') -> Optional[TrainSeats]`

- [ ] **Step 1: Тесты на фикстуре payload**

```python
PAYLOAD = {'Cars': [
    {'CarNumber': '08', 'CarType': 'Compartment', 'CarTypeName': 'КУПЕ',
     'ServiceClassNameRu': '2Э', 'CarPlaceNameRu': 'Нижнее',
     'MinPrice': 3752.6, 'MaxPrice': 3752.6, 'IsForDisabledPersons': False,
     'FreePlacesByCompartments': [{'CompartmentNumber': 4, 'Places': '015'}]},
    {'CarNumber': '08', 'CarType': 'Compartment', 'CarTypeName': 'КУПЕ',
     'ServiceClassNameRu': '2Э', 'CarPlaceNameRu': 'Верхнее',
     'MinPrice': 2573.6, 'MaxPrice': 3015.7, 'IsForDisabledPersons': False,
     'FreePlacesByCompartments': [{'CompartmentNumber': 4, 'Places': '016'}]},
    {'CarNumber': '11', 'CarType': 'Compartment', 'CarTypeName': 'КУПЕ',
     'ServiceClassNameRu': '2Э', 'CarPlaceNameRu': 'Нижнее',
     'MinPrice': 2452.2, 'MaxPrice': 2452.2, 'IsForDisabledPersons': True,
     'FreePlacesByCompartments': [{'CompartmentNumber': 1, 'Places': '001'}]},
]}

def test_describe_exact_price_when_min_equals_max():
    s = TrainSeats(PAYLOAD).describe('lower')
    assert 'Вагон 08' in s and '015' in s and '3752' in s
    assert 'от 3752' not in s

def test_describe_uses_ot_when_price_spread():
    s = TrainSeats(PAYLOAD).describe('upper')
    assert 'от 2573' in s

def test_describe_hides_disabled_by_default():
    assert 'Вагон 11' not in TrainSeats(PAYLOAD).describe('lower')
    assert 'Вагон 11' in TrainSeats(PAYLOAD).describe('lower', include_disabled=True)

def test_seats_returns_none_on_network_error(monkeypatch):
    svc = SeatMapService()
    monkeypatch.setattr(svc, '_fetch', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    assert svc.seats('2000000', '2060000', '2026-09-21T01:26:00', '063В') is None
```

- [ ] **Step 2: Прогнать, убедиться что падают**

Run: `pytest tests/test_seatmap_detail.py -v`
Expected: FAIL — `ImportError: cannot import name 'TrainSeats'`.

- [ ] **Step 3: Реализовать**

`TrainSeats` хранит `payload`, фильтрует строки `Cars` по `IsForDisabledPersons`, делегирует существующим чистым функциям. `describe` формирует блок вида:

```
🚃 Вагон 08 (КУПЕ)
🛏 Место 015 (нижнее)
💰 3752 ₽
```

Цена: `f"{int(mn)} ₽"` при `mn == mx`, иначе `f"от {int(mn)} ₽"`. Лимит `limit=6`, дальше `… и ещё N`.

`SeatMapService.seats()` = `_fetch` в `try/except` + `TrainSeats(payload)`, `None` при ошибке (перенести обработку из `detail_for_berth`).

Четыре старых метода переписать как обёртки над `seats()`, сигнатуры сохранить.

- [ ] **Step 4: Прогнать тесты**

Run: `pytest -q`
Expected: PASS, включая существующие `tests/test_match_seats.py`.

- [ ] **Step 5: Коммит**

```bash
git add services/rzd_seatmap.py tests/test_seatmap_detail.py
git commit -m "refactor: TrainSeats — один сетевой вызов схемы вагонов вместо четырёх методов (#8)"
```

---

### Task 5: `services/monitoring.py` — детальные уведомления и убитый двойной запрос

**Files:**
- Modify: `services/monitoring.py:69` (`count_matched`), `:95` (`_filtered_state`), `:167` (`format_availability_message`)
- Test: `tests/test_monitoring_notification.py` (create)

**Interfaces:**
- Consumes: `TrainSeats`, `SeatMapService.seats()` (Task 4); `include_disabled` (Task 1, 2).
- Produces: уведомление с детализацией для всех фильтров.

- [ ] **Step 1: Тесты**

```python
def test_notification_includes_car_and_seat_for_plain_filter(monkeypatch):
    """Обычный фильтр (не cabin/pair/together) тоже получает детализацию."""
    # подменить SeatMapService.seats на возврат TrainSeats(PAYLOAD)
    ...
    assert 'Вагон 08' in msg and 'Место 015' in msg

def test_seatmap_fetched_once_per_train(monkeypatch):
    calls = []
    # считать вызовы seats() за один цикл check + notify
    ...
    assert len(calls) == 1
```

- [ ] **Step 2: Прогнать, убедиться что падают**

Run: `pytest tests/test_monitoring_notification.py -v`
Expected: FAIL — детализации нет для обычных фильтров; счётчик вызовов == 2.

- [ ] **Step 3: Реализовать**

`count_matched` возвращает `(count, seats)` либо кладёт `TrainSeats` в переданный кэш `dict` по ключу `(train_number, departure)`. `_filtered_state` прокидывает кэш, `format_availability_message` берёт из него готовый `TrainSeats` и только при промахе делает `seats()`.

Прокинуть `subscription.include_disabled` в `match_seats` / `min_price` / `TrainSeats.describe`.

Формат состояния (`"<train>:<matched>"`) не менять.

- [ ] **Step 4: Прогнать тесты**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add services/monitoring.py tests/test_monitoring_notification.py
git commit -m "feat: вагон/место/полка/цена в уведомлениях + один запрос схемы вместо двух (#8)"
```

---

### Task 6: Интеграционный тест на инвариант #9

**Files:**
- Modify: `tests/test_api.py`

- [ ] **Step 1: Тест**

```python
@pytest.mark.skipif(not RUN_INTEGRATION, reason="Integration tests are disabled.")
def test_disabled_group_is_wholly_disabled():
    """Инвариант, на котором стоит #9: помеченная CarGroup целиком инвалидная.

    Если РЖД начнёт смешивать инвалидные места с обычными в одной группе,
    дешёвый предикат станет отбрасывать покупаемые места — тест это поймает.
    """
    ...
    assert group['TotalPlaceQuantity'] == disabled_seats_from_carpricing
```

- [ ] **Step 2: Прогнать**

Run: `RUN_INTEGRATION_TESTS=1 pytest tests/test_api.py -v`
Expected: PASS (использует `verify=rzd_verify()`, см. коммит 8c4a712).

- [ ] **Step 3: Коммит**

```bash
git add tests/test_api.py
git commit -m "test: интеграционный инвариант «инвалидная группа целиком инвалидная» (#9)"
```

---

### Task 7: Полная верификация

- [ ] **Step 1:** `pytest -q` — вся пачка зелёная
- [ ] **Step 2:** `RUN_INTEGRATION_TESTS=1 pytest -q` — включая живой API
- [ ] **Step 3:** Ручная проверка на живом поезде: минимальная цена в выдаче не совпадает с ценой инвалидной группы
- [ ] **Step 4:** Обновить `CLAUDE.md` — правило «инвалидные места отбрасываются группой целиком» и новый шов `TrainSeats`
- [ ] **Step 5:** Закрыть #9 и #8 с ссылкой на коммиты
