# Умные фильтры подписки — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в подписку фильтры по типу вагона / полке / цене, показывать наличие мест при подписке и фильтр-осведомлённый мониторинг; «у окна» — изолированный best-effort модуль (только просмотр).

**Architecture:** Чистая логика матчинга — одна функция `RZDAPIService.match_seats`; презентационная логика фильтров — отдельный модуль `services/filters.py` без зависимостей от aiogram; хендлеры и монитор переиспользуют их. Новые поля подписки/состояния хранятся в SQLite с идемпотентными миграциями.

**Tech Stack:** Python 3, aiogram 3, requests, sqlite3, pytest. Всё на уже доступных данных `train-pricing → CarGroups`.

## Global Constraints

- Язык кода и строк — русский (комментарии, логи, UI). Копировать стиль окружения.
- Ошибки логируются, не бросаются: сервисы/БД возвращают пустые/дефолтные значения.
- Сетевые вызовы РЖД (`requests`) — только через `asyncio.to_thread` в async-контексте.
- Инварианты флоу поиска: единое прогресс-сообщение (`progress_message_id`), очистка `messages_to_delete`, `save_search_state` после каждой мутации.
- callback_data ≤ 64 байт.
- Новые тесты — не `integration`; `pytest -m "not integration"` остаётся зелёным.
- Деплой: коммит в `feat/train-display-and-improvements`; self-hosted runner на Orange Pi раскатывает при push.

---

### Task 1: `match_seats` — единая логика матчинга мест

**Files:**
- Modify: `services/rzd_api.py` (добавить метод в `RZDAPIService`, рядом с `count_seats_breakdown`)
- Test: `tests/test_match_seats.py`

**Interfaces:**
- Produces: `RZDAPIService.match_seats(self, train: dict, car_types=None, berth: str='any', max_price: int=0) -> dict` → `{'total': int, 'lower': int, 'upper': int, 'min_price': float|None, 'by_type': {str: int}}`. Учитывает только `CarGroups` с `AvailabilityIndication=='Available'`. `car_types`: множество кодов `CarType` или None/пусто = любой. `berth`: `'any'|'lower'|'upper'` (низ=`Lower+LowerSide`, верх=`Upper+UpperSide`). `max_price`: ₽, 0 = любая (сравнение с `MinPrice`).

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_match_seats.py
from services.rzd_api import RZDAPIService

api = RZDAPIService()

def _train():
    return {"CarGroups": [
        {"AvailabilityIndication": "Available", "CarType": "Compartment", "CarTypeName": "Купе",
         "PlaceQuantity": 10, "LowerPlaceQuantity": 6, "UpperPlaceQuantity": 4,
         "LowerSidePlaceQuantity": 0, "UpperSidePlaceQuantity": 0, "MinPrice": 5200.0},
        {"AvailabilityIndication": "Available", "CarType": "ReservedSeat", "CarTypeName": "Плац",
         "PlaceQuantity": 8, "LowerPlaceQuantity": 3, "UpperPlaceQuantity": 3,
         "LowerSidePlaceQuantity": 1, "UpperSidePlaceQuantity": 1, "MinPrice": 2200.0},
        {"AvailabilityIndication": "NotAvailable", "CarType": "Soft", "CarTypeName": "Люкс",
         "PlaceQuantity": 99, "MinPrice": 100.0},
    ]}

def test_no_filters_counts_all_available():
    r = api.match_seats(_train())
    assert r["total"] == 18            # 10 + 8, недоступный не считается
    assert r["lower"] == 10            # 6 + (3+1 боковой)
    assert r["upper"] == 8             # 4 + (3+1 боковой)
    assert r["min_price"] == 2200.0
    assert r["by_type"] == {"Купе": 10, "Плац": 8}

def test_filter_car_type():
    r = api.match_seats(_train(), car_types=["Compartment"])
    assert r["total"] == 10
    assert r["by_type"] == {"Купе": 10}

def test_filter_berth_lower():
    r = api.match_seats(_train(), berth="lower")
    # учитываются только группы, где есть нижние; считаем нижние места
    assert r["total"] == 18 and r["lower"] == 10

def test_filter_max_price():
    r = api.match_seats(_train(), max_price=3000)
    assert r["total"] == 8             # только Плац (2200 <= 3000)
    assert r["by_type"] == {"Плац": 8}

def test_empty_train():
    r = api.match_seats({})
    assert r == {"total": 0, "lower": 0, "upper": 0, "min_price": None, "by_type": {}}
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python3 -m pytest tests/test_match_seats.py -q`
Expected: FAIL (`AttributeError: 'RZDAPIService' object has no attribute 'match_seats'`)

- [ ] **Step 3: Реализовать метод**

В `services/rzd_api.py`, внутри класса `RZDAPIService` (после `count_seats_breakdown`):

```python
    def match_seats(self, train: Dict, car_types=None, berth: str = 'any',
                    max_price: int = 0) -> Dict:
        """Считает места, подходящие под фильтры подписки.

        car_types: коллекция кодов CarType (или None/пусто = любой).
        berth: 'any' | 'lower' | 'upper' (низ=Lower+LowerSide, верх=Upper+UpperSide).
        max_price: потолок цены в рублях (0 = любая), сравнение с MinPrice группы.
        """
        result = {'total': 0, 'lower': 0, 'upper': 0, 'min_price': None, 'by_type': {}}
        wanted = set(car_types) if car_types else None
        try:
            for cg in train.get('CarGroups', []):
                if cg.get('AvailabilityIndication') != 'Available':
                    continue
                if wanted is not None and cg.get('CarType') not in wanted:
                    continue
                price = cg.get('MinPrice')
                if max_price and price and price > max_price:
                    continue
                lower = (cg.get('LowerPlaceQuantity', 0) or 0) + (cg.get('LowerSidePlaceQuantity', 0) or 0)
                upper = (cg.get('UpperPlaceQuantity', 0) or 0) + (cg.get('UpperSidePlaceQuantity', 0) or 0)
                if berth == 'lower' and lower <= 0:
                    continue
                if berth == 'upper' and upper <= 0:
                    continue
                qty = cg.get('PlaceQuantity', 0) or 0
                result['total'] += qty
                result['lower'] += lower
                result['upper'] += upper
                name = cg.get('CarTypeName') or cg.get('CarType') or '?'
                result['by_type'][name] = result['by_type'].get(name, 0) + qty
                if price and (result['min_price'] is None or price < result['min_price']):
                    result['min_price'] = price
        except Exception as e:
            logger.error(f"Ошибка match_seats: {e}")
        return result
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `python3 -m pytest tests/test_match_seats.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Коммит**

```bash
git add services/rzd_api.py tests/test_match_seats.py
git commit -m "feat: match_seats — фильтрация мест по вагону/полке/цене"
```

---

### Task 2: `services/filters.py` — пресеты, тогглы, клавиатура, сводка

**Files:**
- Create: `services/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: ничего.
- Produces:
  - `CAR_TYPE_LABELS: dict[str,str]`, `CAR_TYPE_ORDER: list[str]`, `PRICE_PRESETS: list[int]`
  - `toggle_car_type(csv: str, code: str) -> str`
  - `parse_filter_callback(data: str) -> tuple[str,str] | None` → `('car'|'berth'|'price', value)`
  - `format_filter_summary(car_types: str, berth: str, max_price: int) -> str`
  - `build_filter_keyboard(car_types: str, berth: str, max_price: int) -> list`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_filters.py
from services import filters as f

def test_toggle_car_type_add_remove():
    assert f.toggle_car_type("", "Compartment") == "Compartment"
    assert f.toggle_car_type("Compartment", "ReservedSeat") in ("Compartment,ReservedSeat", "ReservedSeat,Compartment")
    assert f.toggle_car_type("Compartment,ReservedSeat", "Compartment") == "ReservedSeat"

def test_parse_filter_callback():
    assert f.parse_filter_callback("flt_car_Compartment") == ("car", "Compartment")
    assert f.parse_filter_callback("flt_berth_lower") == ("berth", "lower")
    assert f.parse_filter_callback("flt_price_5000") == ("price", "5000")
    assert f.parse_filter_callback("subscribe_filtered") is None

def test_format_filter_summary():
    assert f.format_filter_summary("", "any", 0) == "любые места"
    assert f.format_filter_summary("Compartment", "lower", 8000) == "Купе · нижнее · до 8000 ₽"
    assert f.format_filter_summary("Compartment,ReservedSeat", "upper", 0) == "Купе, Плац · верхнее"

def test_build_filter_keyboard_marks_selected():
    kb = f.build_filter_keyboard("Compartment", "lower", 5000)
    flat = [b for row in kb for b in row]
    texts = {b["text"]: b["callback_data"] for b in flat}
    assert "✅ Купе" in texts and texts["✅ Купе"] == "flt_car_Compartment"
    assert "✅ Низ" in texts
    assert "✅ ≤5000" in texts
    assert any(b["callback_data"] == "subscribe_filtered" for b in flat)
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python3 -m pytest tests/test_filters.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'services.filters'`)

- [ ] **Step 3: Реализовать модуль**

```python
# services/filters.py
"""Пресеты и презентационная логика фильтров подписки (без зависимостей от aiogram)."""

CAR_TYPE_LABELS = {
    "Compartment": "Купе",
    "ReservedSeat": "Плац",
    "Sedentary": "СИД",
    "Soft": "Люкс",
}
CAR_TYPE_ORDER = ["Compartment", "ReservedSeat", "Sedentary", "Soft"]
PRICE_PRESETS = [3000, 5000, 8000]
_BERTH_SUMMARY = {"lower": "нижнее", "upper": "верхнее"}
_BERTH_BTN = {"lower": "Низ", "upper": "Верх", "any": "Любая"}


def toggle_car_type(csv: str, code: str) -> str:
    """Добавляет/убирает код типа вагона в CSV-строке."""
    items = [c for c in (csv or "").split(",") if c]
    if code in items:
        items.remove(code)
    else:
        items.append(code)
    # сохраняем стабильный порядок
    items = [c for c in CAR_TYPE_ORDER if c in items]
    return ",".join(items)


def parse_filter_callback(data: str):
    """'flt_<kind>_<value>' -> (kind, value); иначе None."""
    if not data or not data.startswith("flt_"):
        return None
    parts = data.split("_", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


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


def build_filter_keyboard(car_types: str, berth: str, max_price: int) -> list:
    """Inline-клавиатура тогглов фильтров."""
    codes = set(c for c in (car_types or "").split(",") if c)

    car_row = []
    for code in CAR_TYPE_ORDER:
        label = CAR_TYPE_LABELS[code]
        text = f"✅ {label}" if code in codes else label
        car_row.append({"text": text, "callback_data": f"flt_car_{code}"})

    berth_row = []
    for val in ("lower", "upper", "any"):
        text = _BERTH_BTN[val]
        if berth == val:
            text = f"✅ {text}"
        berth_row.append({"text": text, "callback_data": f"flt_berth_{val}"})

    price_row = []
    for p in PRICE_PRESETS:
        text = f"≤{p}"
        if max_price == p:
            text = f"✅ {text}"
        price_row.append({"text": text, "callback_data": f"flt_price_{p}"})
    any_price = "Любая" if max_price else "✅ Любая"
    price_row.append({"text": any_price, "callback_data": "flt_price_0"})

    return [
        car_row,
        berth_row,
        price_row,
        [{"text": "🔔 Подписаться", "callback_data": "subscribe_filtered"}],
    ]
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `python3 -m pytest tests/test_filters.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Коммит**

```bash
git add services/filters.py tests/test_filters.py
git commit -m "feat: services/filters — тогглы/сводка/клавиатура фильтров"
```

---

### Task 3: Поля БД и миграции (подписка + состояние поиска)

**Files:**
- Modify: `database/models.py` (`Subscription`, `SearchState`)
- Modify: `database/manager.py` (миграции, `create_subscription`, `get_user_subscriptions`, `get_active_subscriptions`, `get_subscription`, `save_search_state`, `get_search_state`)
- Test: `tests/test_filters_db.py`

**Interfaces:**
- Consumes: —
- Produces: `Subscription.berth: str='any'`, `Subscription.max_price: int=0`; `SearchState.filter_car_types: str=''`, `SearchState.filter_berth: str='any'`, `SearchState.filter_max_price: int=0`, `SearchState.selected_train_cargroups: str=''`. Тип вагона подписки хранится в существующем `Subscription.car_types` (CSV кодов).

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_filters_db.py
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python3 -m pytest tests/test_filters_db.py -q`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'berth'`)

- [ ] **Step 3: Добавить поля в dataclasses**

В `database/models.py` в конец `Subscription` (после `created_at`):

```python
    berth: str = 'any'
    max_price: int = 0
```

В конец `SearchState` (после `messages_to_delete`):

```python
    filter_car_types: str = ''
    filter_berth: str = 'any'
    filter_max_price: int = 0
    selected_train_cargroups: str = ''
```

- [ ] **Step 4: Миграции в `init_database`**

В `database/manager.py`, в `init_database()` перед `conn.commit()` добавить (по образцу существующей миграции `messages_to_delete`):

```python
            # Миграции новых колонок фильтров (для старых БД)
            try:
                cursor.execute("PRAGMA table_info(subscriptions)")
                cols = [r[1] for r in cursor.fetchall()]
                if 'berth' not in cols:
                    cursor.execute("ALTER TABLE subscriptions ADD COLUMN berth TEXT DEFAULT 'any'")
                if 'max_price' not in cols:
                    cursor.execute("ALTER TABLE subscriptions ADD COLUMN max_price INTEGER DEFAULT 0")
                cursor.execute("PRAGMA table_info(search_states)")
                scols = [r[1] for r in cursor.fetchall()]
                for col, ddl in (
                    ('filter_car_types', "ALTER TABLE search_states ADD COLUMN filter_car_types TEXT DEFAULT ''"),
                    ('filter_berth', "ALTER TABLE search_states ADD COLUMN filter_berth TEXT DEFAULT 'any'"),
                    ('filter_max_price', "ALTER TABLE search_states ADD COLUMN filter_max_price INTEGER DEFAULT 0"),
                    ('selected_train_cargroups', "ALTER TABLE search_states ADD COLUMN selected_train_cargroups TEXT DEFAULT ''"),
                ):
                    if col not in scols:
                        cursor.execute(ddl)
            except Exception as mig_e:
                logger.error(f"Ошибка миграции колонок фильтров: {mig_e}")
```

- [ ] **Step 5: `create_subscription` — добавить колонки**

В `create_subscription` заменить INSERT на:

```python
            cursor.execute('''
                INSERT INTO subscriptions
                (user_id, origin_code, origin_name, destination_code, destination_name,
                 departure_date, train_numbers, car_types, min_seats, adult_passengers,
                 children_passengers, interval_minutes, berth, max_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                subscription.user_id, subscription.origin_code, subscription.origin_name,
                subscription.destination_code, subscription.destination_name,
                subscription.departure_date, subscription.train_numbers, subscription.car_types,
                subscription.min_seats, subscription.adult_passengers,
                subscription.children_passengers, subscription.interval_minutes,
                subscription.berth, subscription.max_price
            ))
```

- [ ] **Step 6: Три SELECT-метода подписок — читать новые колонки**

В `get_user_subscriptions`, `get_active_subscriptions`, `get_subscription` в списке колонок SELECT добавить `, berth, max_price` в конец (после `created_at`), и в конструкторе `Subscription(...)` добавить:

```python
                    berth=row[15] if row[15] is not None else 'any',
                    max_price=row[16] if row[16] is not None else 0,
```

(индексы 15/16 — следующие после `created_at`=14; во всех трёх методах список колонок одинаков и `created_at` идёт последним перед добавленными.)

- [ ] **Step 7: `save_search_state` / `get_search_state` — новые колонки**

В `save_search_state` расширить INSERT OR REPLACE: добавить в список колонок `filter_car_types, filter_berth, filter_max_price, selected_train_cargroups`, в VALUES — 4 плейсхолдера, в кортеж значений (после `messages_to_delete_str`):

```python
                getattr(search_state, 'filter_car_types', ''),
                getattr(search_state, 'filter_berth', 'any'),
                getattr(search_state, 'filter_max_price', 0),
                getattr(search_state, 'selected_train_cargroups', ''),
```

В `get_search_state` добавить эти колонки в SELECT (после `messages_to_delete`) и в конструктор `SearchState(...)`:

```python
                    filter_car_types=row[16] or '',
                    filter_berth=row[17] or 'any',
                    filter_max_price=row[18] or 0,
                    selected_train_cargroups=row[19] or '',
```

(текущий SELECT возвращает `messages_to_delete` индексом 15; новые — 16..19.)

- [ ] **Step 8: Запустить тесты**

Run: `python3 -m pytest tests/test_filters_db.py -q`
Expected: PASS (3 passed)

- [ ] **Step 9: Регресс всей быстрой сюиты**

Run: `python3 -m pytest -q -m "not integration"`
Expected: PASS (все прежние + новые)

- [ ] **Step 10: Коммит**

```bash
git add database/models.py database/manager.py tests/test_filters_db.py
git commit -m "feat: поля фильтров подписки в БД + миграции"
```

---

### Task 4: Панель фильтров при подписке (`handlers/search.py`)

**Files:**
- Modify: `handlers/search.py` (`handle_select_train`, `handle_callback`, новые `handle_filter_toggle`, `subscribe_filtered`; helper `_render_filter_panel`)
- Test: `tests/test_filter_panel.py`

**Interfaces:**
- Consumes: `RZDAPIService.match_seats` (Task 1); `services.filters` (Task 2); поля `SearchState` (Task 3).
- Produces: helper `SearchHandler._panel_text(self, breakdown: dict, matched: dict, filter_summary: str) -> str` (чистая сборка текста — тестируется); callback'и `flt_*` и `subscribe_filtered`.

- [ ] **Step 1: Написать падающий тест на чистый сборщик текста**

```python
# tests/test_filter_panel.py
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python3 -m pytest tests/test_filter_panel.py -q`
Expected: FAIL (`AttributeError: ... '_panel_text'`)

- [ ] **Step 3: Реализовать `_panel_text` + импорты**

В начало `handlers/search.py` к импортам добавить:

```python
import json
from services import filters as flt
```

В класс `SearchHandler` добавить метод:

```python
    def _panel_text(self, breakdown: dict, matched: dict, filter_summary: str) -> str:
        by_type = " · ".join(f"{k} {v}" for k, v in breakdown.get("by_type", {}).items()) or "—"
        price = breakdown.get("min_price")
        price_str = f" · от {price:.0f} ₽" if price else ""
        return (
            f"🚆 <b>Наличие мест</b>\n"
            f"Найдено мест: <b>{breakdown.get('total', 0)}</b>\n"
            f"{by_type}  |  низ {breakdown.get('lower', 0)} / верх {breakdown.get('upper', 0)}{price_str}\n\n"
            f"Фильтр: <b>{filter_summary}</b>\n"
            f"Под фильтр подходит: <b>{matched.get('total', 0)}</b> мест\n\n"
            f"Настройте фильтр кнопками ниже и нажмите «Подписаться»."
        )
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `python3 -m pytest tests/test_filter_panel.py -q`
Expected: PASS

- [ ] **Step 5: Перевести `handle_select_train` на показ панели**

Заменить тело `handle_select_train` так, чтобы после установки `selected_train_number`/`search_step='done'`: повторно запросить train-pricing (через `asyncio.to_thread`), найти поезд по номеру, сохранить его `CarGroups` в `search_state.selected_train_cargroups` (JSON), сбросить `filter_car_types=''`, `filter_berth='any'`, `filter_max_price=0`, затем отрисовать панель через новый `_render_filter_panel` (Step 6). Полный код:

```python
    async def handle_select_train(self, callback: CallbackQuery):
        """Выбор поезда -> показываем панель наличия и фильтров"""
        try:
            data = callback.data
            user_id = callback.from_user.id
            parts = data.split('_', 3)
            if len(parts) < 3:
                await callback.answer('❌ Ошибка при выборе поезда')
                return
            train_number = parts[2]
            train_info = parts[3] if len(parts) > 3 else train_number
            search_state = self.db_manager.get_search_state(user_id)
            if not search_state:
                await callback.answer('❌ Ошибка состояния поиска')
                return
            await callback.answer("Загружаю наличие…")
            trains_data = await asyncio.to_thread(
                self.rzd_api.search_trains,
                origin_code=search_state.origin_code,
                destination_code=search_state.destination_code,
                departure_date=search_state.departure_date,
                adult_passengers=search_state.adult_passengers,
                children_passengers=search_state.children_passengers,
            )
            cargroups = []
            for tr in trains_data.get('trains', []):
                if self.rzd_api.extract_train_info(tr)['number'] == train_number:
                    cargroups = tr.get('CarGroups', [])
                    break
            search_state.selected_train_number = train_number
            search_state.selected_train_info = train_info
            search_state.search_step = 'done'
            search_state.selected_train_cargroups = json.dumps(cargroups, ensure_ascii=False)
            search_state.filter_car_types = ''
            search_state.filter_berth = 'any'
            search_state.filter_max_price = 0
            self.db_manager.save_search_state(search_state)
            await self._render_filter_panel(callback.message.chat.id, search_state)
        except Exception as e:
            logger.error(f'Ошибка выбора поезда: {e}')
            await callback.answer('❌ Ошибка при выборе поезда')
```

- [ ] **Step 6: Добавить `_render_filter_panel`**

```python
    async def _render_filter_panel(self, chat_id: int, search_state: SearchState):
        """Рисует/обновляет панель наличия и фильтров (edit-in-place)."""
        try:
            cargroups = json.loads(search_state.selected_train_cargroups or '[]')
        except Exception:
            cargroups = []
        train = {'CarGroups': cargroups}
        car_types = [c for c in (search_state.filter_car_types or '').split(',') if c]
        breakdown = self.rzd_api.match_seats(train)
        matched = self.rzd_api.match_seats(
            train, car_types=car_types or None,
            berth=search_state.filter_berth, max_price=search_state.filter_max_price,
        )
        summary = flt.format_filter_summary(
            search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price
        )
        text = self._panel_text(breakdown, matched, summary)
        keyboard = flt.build_filter_keyboard(
            search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price
        )
        if search_state.progress_message_id:
            await self.notification_service.edit_message(
                chat_id, search_state.progress_message_id, text, keyboard=keyboard, parse_mode='HTML'
            )
        else:
            sent_id = await self.notification_service.send_message_with_keyboard(chat_id, text, keyboard)
            if sent_id:
                search_state.progress_message_id = sent_id
                self.db_manager.save_search_state(search_state)
```

- [ ] **Step 7: Диспатч `flt_*` и `subscribe_filtered` в `handle_callback`**

В `handle_callback` (внутри цепочки `if/elif`) добавить перед `else:`:

```python
            elif data.startswith("flt_"):
                await self.handle_filter_toggle(callback)
            elif data == "subscribe_filtered":
                await self.subscribe_to_selected_train(callback)
```

- [ ] **Step 8: Реализовать `handle_filter_toggle`**

```python
    async def handle_filter_toggle(self, callback: CallbackQuery):
        """Тоггл фильтра: обновляем состояние и перерисовываем панель без запроса к РЖД."""
        try:
            user_id = callback.from_user.id
            parsed = flt.parse_filter_callback(callback.data)
            search_state = self.db_manager.get_search_state(user_id)
            if not parsed or not search_state:
                await callback.answer()
                return
            kind, value = parsed
            if kind == 'car':
                search_state.filter_car_types = flt.toggle_car_type(search_state.filter_car_types, value)
            elif kind == 'berth':
                search_state.filter_berth = value
            elif kind == 'price':
                search_state.filter_max_price = int(value)
            self.db_manager.save_search_state(search_state)
            await self._render_filter_panel(callback.message.chat.id, search_state)
            await callback.answer()
        except Exception as e:
            logger.error(f"Ошибка тоггла фильтра: {e}")
            await callback.answer()
```

- [ ] **Step 9: Записывать фильтры в подписку**

В `subscribe_to_selected_train` при создании `Subscription(...)` добавить аргументы (берём из `search_state`):

```python
                car_types=search_state.filter_car_types,
                berth=search_state.filter_berth,
                max_price=search_state.filter_max_price,
```

(заменив существующий `car_types=search_state.car_types`). В тексте подтверждения добавить строку:

```python
                    f"Фильтр: {flt.format_filter_summary(search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price)}\n"
```

- [ ] **Step 10: Прогон тестов + проверка импорта**

Run: `python3 -m pytest tests/test_filter_panel.py -q && python3 -c "import handlers.search"`
Expected: PASS и `import` без ошибок

- [ ] **Step 11: Коммит**

```bash
git add handlers/search.py tests/test_filter_panel.py
git commit -m "feat: панель наличия и фильтров при подписке"
```

---

### Task 5: Фильтр-осведомлённый мониторинг и уведомления (`services/monitoring.py`)

**Files:**
- Modify: `services/monitoring.py` (`check_single_subscription`, `format_availability_message`)
- Test: `tests/test_monitoring_filters.py`

**Interfaces:**
- Consumes: `RZDAPIService.match_seats` (Task 1), `services.filters.format_filter_summary` (Task 2), поля `Subscription` (Task 3).
- Produces: статический метод `MonitoringService._filtered_state(rzd_api, subscription, trains: list) -> tuple[list, str]` → `(подходящие_поезда, строка_состояния)`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_monitoring_filters.py
from services.monitoring import MonitoringService
from services.rzd_api import RZDAPIService
from database import Subscription
from datetime import datetime

def _sub(**kw):
    base = dict(id=1, user_id=1, origin_code="A", origin_name="A", destination_code="B",
                destination_name="B", departure_date="2026-07-01T00:00:00", train_numbers="",
                car_types="", min_seats=1, adult_passengers=1, children_passengers=0,
                interval_minutes=5, is_active=True, created_at=datetime.now(),
                berth="any", max_price=0)
    base.update(kw)
    return Subscription(**base)

def _trains():
    return [{"TrainNumber": "001A", "CarGroups": [
        {"AvailabilityIndication": "Available", "CarType": "Compartment", "CarTypeName": "Купе",
         "PlaceQuantity": 4, "LowerPlaceQuantity": 2, "UpperPlaceQuantity": 2, "MinPrice": 9000.0},
        {"AvailabilityIndication": "Available", "CarType": "ReservedSeat", "CarTypeName": "Плац",
         "PlaceQuantity": 5, "LowerPlaceQuantity": 5, "UpperPlaceQuantity": 0, "MinPrice": 2000.0},
    ]}]

def test_filtered_state_price_cap():
    api = RZDAPIService()
    trains, state = MonitoringService._filtered_state(api, _sub(max_price=3000), _trains())
    assert len(trains) == 1                  # есть подходящие (Плац 2000<=3000)
    assert state == "001A:5"                 # под фильтр 5 мест

def test_filtered_state_none_match():
    api = RZDAPIService()
    trains, state = MonitoringService._filtered_state(api, _sub(car_types="Soft"), _trains())
    assert trains == [] and state == "001A:0"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python3 -m pytest tests/test_monitoring_filters.py -q`
Expected: FAIL (`AttributeError: ... '_filtered_state'`)

- [ ] **Step 3: Реализовать `_filtered_state` и подключить в `check_single_subscription`**

Добавить в `MonitoringService`:

```python
    @staticmethod
    def _filtered_state(rzd_api, subscription, trains: list):
        """Возвращает (подходящие_поезда, строка_состояния) с учётом фильтров подписки."""
        car_types = [c for c in (subscription.car_types or '').split(',') if c]
        available, parts = [], []
        for train in trains:
            number = rzd_api.extract_train_info(train)['number']
            if subscription.train_numbers and number not in subscription.train_numbers.split(','):
                continue
            m = rzd_api.match_seats(
                train, car_types=car_types or None,
                berth=getattr(subscription, 'berth', 'any'),
                max_price=getattr(subscription, 'max_price', 0),
            )
            if m['total'] >= max(1, subscription.min_seats):
                available.append(train)
            parts.append(f"{number}:{m['total']}")
        return available, ",".join(sorted(parts))
```

В `check_single_subscription` заменить блок подсчёта `available_trains`/`current_state` на:

```python
            available_trains, current_state = self._filtered_state(
                self.rzd_api, subscription, trains_data['trains']
            )
            last_state = self.db_manager.get_subscription_last_state(subscription.id)
            if available_trains and current_state != (last_state or ""):
                await self.send_availability_notification(subscription, available_trains)
            self.db_manager.save_subscription_last_state(subscription.id, current_state)
```

(удалив старый цикл с `count_available_seats`).

- [ ] **Step 4: Добавить сводку фильтра в уведомление**

В `services/monitoring.py` импорт `from services.filters import format_filter_summary`. В `format_availability_message` после строки даты добавить:

```python
        summary = format_filter_summary(
            subscription.car_types, getattr(subscription, 'berth', 'any'),
            getattr(subscription, 'max_price', 0),
        )
        message += f"Фильтр: {summary}\n\n"
```

- [ ] **Step 5: Прогон тестов**

Run: `python3 -m pytest tests/test_monitoring_filters.py -q`
Expected: PASS (2 passed)

- [ ] **Step 6: Коммит**

```bash
git add services/monitoring.py tests/test_monitoring_filters.py
git commit -m "feat: фильтр-осведомлённый мониторинг и уведомления"
```

---

### Task 6: «У окна» — изолированный best-effort модуль (только просмотр)

**Files:**
- Create: `services/rzd_seatmap.py`
- Test: `tests/test_seatmap.py`

**Interfaces:**
- Consumes: `config` (URL/User-Agent).
- Produces: `parse_window_counts(payload: dict) -> dict | None` → `{'window': int, 'other': int}` или `None` если форма неизвестна; `SeatMapService.get_window_counts(train_number, car_type, origin, destination, departure_date) -> dict | None` (ловит все ошибки → `None`).

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_seatmap.py
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
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python3 -m pytest tests/test_seatmap.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'services.rzd_seatmap'`)

- [ ] **Step 3: Реализовать модуль**

```python
# services/rzd_seatmap.py
"""Best-effort определение мест «у окна» через схему вагона РЖД.

Используется ТОЛЬКО при просмотре/подписке, никогда в цикле мониторинга.
Эндпоинт car-pricing требует доревёрса параметров; до этого _fetch может
возвращать пустое/ошибку, а публичные функции — None (UI показывает «н/д»).
"""
import logging
import requests

from config import config

logger = logging.getLogger(__name__)

CAR_PRICING_URL = "https://ticket.rzd.ru/api/v1/railway-service/prices/car-pricing"


def parse_window_counts(payload: dict):
    """Считает доступные места у окна / не у окна из схемы вагона.

    Возвращает None, если форма ответа не распознана (тогда UI -> «н/д»).
    """
    try:
        cars = payload.get("Cars")
        if not cars:
            return None
        window = other = 0
        seen = False
        for car in cars:
            for pl in car.get("Places", []) or []:
                if "Window" not in pl:
                    continue
                seen = True
                if not pl.get("IsAvailable", True):
                    continue
                if pl.get("Window"):
                    window += 1
                else:
                    other += 1
        if not seen:
            return None
        return {"window": window, "other": other}
    except Exception as e:
        logger.error(f"Ошибка парсинга схемы мест: {e}")
        return None


class SeatMapService:
    """Обёртка над car-pricing РЖД (best-effort)."""

    def __init__(self):
        self.user_agent = config.USER_AGENT

    def _fetch(self, train_number, car_type, origin, destination, departure_date) -> dict:
        params = {
            "service_provider": "B2B_RZD",
            "getByLocalTime": "true",
            "origin": origin,
            "destination": destination,
            "departureDate": departure_date,
            "trainNumber": train_number,
            "carType": car_type,
            "specialPlacesDemand": "StandardPlacesAndForDisabledPersons",
            "carIssuingType": "Passenger",
            "adultPassengersQuantity": 1,
        }
        headers = {"Accept": "application/json, text/plain, */*", "User-Agent": self.user_agent}
        resp = requests.get(CAR_PRICING_URL, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_window_counts(self, train_number, car_type, origin, destination, departure_date):
        """Возвращает {'window':int,'other':int} или None (best-effort)."""
        try:
            return parse_window_counts(self._fetch(train_number, car_type, origin, destination, departure_date))
        except Exception as e:
            logger.error(f"Схема мест недоступна: {e}")
            return None
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `python3 -m pytest tests/test_seatmap.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Реверс параметров car-pricing на живых данных (Orange Pi)**

Подобрать рабочие параметры/метод `car-pricing` (на зонде GET вернул `INTERNAL_ERROR`; вероятно нужен POST с телом или доп. поля), выполняя запросы С Orange Pi (только он видит РЖД):

```bash
ssh -i ~/.ssh/trainparser_claude orangepi@192.168.1.77 \
  'curl -s -X POST "https://ticket.rzd.ru/api/v1/railway-service/prices/car-pricing" \
   -H "Content-Type: application/json" -H "User-Agent: Mozilla/5.0" \
   -d "{...подобрать тело...}" --max-time 30 | head -c 600'
```

Когда получен валидный ответ — сверить реальные имена полей места (есть ли признак окна) с `parse_window_counts`; при расхождении поправить парсер и его тест (фикстуру) под реальную форму. Если окна в публичном ответе отсутствуют — оставить модуль как есть (всегда `None`), зафиксировать это в докстринге и не тратить время дальше.

- [ ] **Step 6: Подключить строку «у окна» в панель (view-only)**

В `handlers/search.py._render_filter_panel` после расчёта `breakdown` добавить (best-effort, без падений):

```python
        window_line = ""
        try:
            from services.rzd_seatmap import SeatMapService
            wc = await asyncio.to_thread(
                SeatMapService().get_window_counts,
                search_state.selected_train_number,
                (car_types[0] if car_types else (cargroups[0].get('CarType') if cargroups else '')),
                search_state.origin_code, search_state.destination_code, search_state.departure_date,
            )
            window_line = f"\nУ окна: {wc['window']} (не у окна: {wc['other']})" if wc else "\nУ окна: н/д"
        except Exception:
            window_line = "\nУ окна: н/д"
```

и добавить `window_line` в конец первого блока `_panel_text` (передать аргументом или дописать к тексту перед строкой «Фильтр»). Простейше — дописать в `_render_filter_panel`:

```python
        text = self._panel_text(breakdown, matched, summary) + window_line
```

- [ ] **Step 7: Прогон всей быстрой сюиты + импорт**

Run: `python3 -m pytest -q -m "not integration" && python3 -c "import handlers.search, services.monitoring"`
Expected: PASS, импорт без ошибок

- [ ] **Step 8: Коммит**

```bash
git add services/rzd_seatmap.py tests/test_seatmap.py handlers/search.py
git commit -m "feat: best-effort у окна (только просмотр) + строка в панели"
```

---

## Self-Review

**Spec coverage:**
- Показ наличия при подписке → Task 4 (панель `_panel_text`/`_render_filter_panel`). ✓
- Фильтры вагон/полка/цена + хранение → Task 1 (match) + Task 2 (UI) + Task 3 (БД). ✓
- Живой пересчёт без запросов → Task 4 (`_render_filter_panel` из кэша `selected_train_cargroups`). ✓
- Фильтр-осведомлённый мониторинг/уведомления + «Проверить сейчас» → Task 5 (монитор). «Проверить сейчас» уже использует `match_seats`-совместимый показ; при необходимости обновится по факту (использует те же поля подписки). ✓
- «У окна» best-effort, только просмотр → Task 6. ✓
- Тесты не-integration, миграции идемпотентны → Task 3/все. ✓

**Placeholder scan:** код приведён в каждом шаге; единственное «подобрать тело» — в Task 6 Step 5 это и есть исследовательская задача (реверс эндпоинта), а не заглушка кода; парсер и его тест конкретны.

**Type consistency:** `match_seats(train, car_types, berth, max_price)` единообразно вызывается в Task 4/5; `format_filter_summary(car_types, berth, max_price)` — в Task 4/5; поля `SearchState`/`Subscription` из Task 3 совпадают с использованием в Task 4/5.

## Замечание по «Проверить сейчас»

`check_subscription_now` (в `handlers/search.py`) после Task 5 стоит привести к тем же фильтрам: считать через `match_seats` с `subscription.car_types/berth/max_price` и показывать сводку `format_filter_summary`. Это малый правок в рамках Task 5 (тот же модуль импортов) — добавить при реализации Task 5 Step 4, файл `handlers/search.py`.
