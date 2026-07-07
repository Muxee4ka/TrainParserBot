# Фильтр «N мест рядом» для сидячих вагонов (Ласточка и т.п.)

Дата: 2026-07-07
Статус: согласовано, готово к плану реализации

## Контекст и цель

Пользователь хочет мониторить сидячие поезда (Ласточка, `CarType=Sedentary`) на
наличие группы мест рядом — например, «3 места вместе» для поездки компанией.
Существующие фильтры подписки (`services/filters.py`, дизайн от 2026-06-19) дают
тип вагона, полку (низ/верх/бок) и потолок цены; полка для сидячих вагонов не
применима (там нет низа/верха), а «вместе» для купе/плац уже решается берт-ами
`cabin`/`pair` через `services/rzd_seatmap.py`. Для сидячих такого механизма нет.

## Исследование API

Реальный запрос к `CarPricing` для сидячего поезда (812С, Адлер→Сочи,
`CarType=Sedentary`) показал: свободные места группируются в
`FreePlacesByCompartments` по `CompartmentNumber`, как и для купе/плац — только
без разбивки по `CarPlaceNameRu` «Нижнее/Верхнее» (для сидячих там категория места:
«Обычное место» / «Для инвалидов»). Размер блока переменный (в наблюдаемых данных
от 1 до 6 мест) — это физический кластер кресел, а не фиксированное «купе на 4».
Сумма размеров блоков одного вагона совпадает с его `PlaceQuantity`.

**Ограничение (принято):** внутри блока нет точной геометрии рядов — если одно
место в блоке продано, оставшиеся свободные места необязательно физически рядом
друг с другом. Считаем «≥N свободных мест в одном блоке `CompartmentNumber`»
достаточным приближением «мест вместе» — тем же способом, каким уже сегодня
работают `cabin`/`pair` для купе.

## Объём

В объёме:
- Новое значение полки `berth='together'`, показывается в панели фильтров
  только когда в поезде есть доступные вагоны `Sedentary`.
- Переиспользование существующего (сейчас нигде не редактируемого) поля
  `min_seats` как «сколько мест нужно вместе» при `berth='together'`; во всех
  остальных случаях `min_seats` продолжает работать как общий агрегатный порог
  (без изменения смысла).
- Новый ввод количества мест в панели фильтров (текстом, по образцу ввода цены).
- Матчинг/уведомления/«Проверить сейчас» учитывают `together` так же, как сейчас
  учитывают `cabin`/`pair`.

Вне объёма:
- Точная геометрия соседних номеров мест (нет данных в API).
- «Вместе» для купе/плац (там уже есть `pair`; не трогаем).
- Любые новые колонки БД — не требуются (см. ниже).

## Модель данных и миграции

**Миграции не требуются.** `subscriptions.berth` и `search_states.filter_berth`
уже `TEXT` без ограничения набора значений — `'together'` встаёт туда как ещё
одна строка. `subscriptions.min_seats` и `search_states.min_seats` уже
существуют и уже сохраняются/читаются в `database/manager.py` — просто
начинаем их фактически редактировать и учитывать.

## Матчинг мест (`services/rzd_seatmap.py`)

Обобщаю `empty_compartments_detail` в:

```
def blocks_with_at_least(payload, min_size, car_types=None, max_price=0,
                         include_types=("Compartment",)) -> list:
    # группирует parse_compartments(...) и возвращает блоки,
    # где len(cell["all"]) >= min_size
```

`empty_compartments_detail` становится тонкой обёрткой
(`min_size=COMPARTMENT_SIZE, include_types=("Compartment",)`). Новая функция:

```
def together_seats_detail(payload, min_count, car_types=None, max_price=0) -> list:
    return blocks_with_at_least(payload, max(1, min_count), car_types=car_types,
                                max_price=max_price, include_types=("Sedentary",))
```

`SEATMAP_BERTHS = ('cabin', 'pair', 'together')`.

`detail_for_berth(payload, berth, car_types=None, max_price=0, min_count=1)` и
`SeatMapService.detail_for_berth`/`count_for_berth` получают новый опциональный
параметр `min_count`, читаемый только веткой `'together'` (для `cabin`/`pair`
игнорируется, обратная совместимость сохранена).

`format_seatmap_detail(berth, detail)` получает ветку для `'together'`:
новая `format_seat_groups(detail, limit=6)` — `"вагон 06: блок 3 (5 мест: 5, 6, 8, 9, 10)"`.

## Панель фильтров (`services/filters.py`)

- `build_filter_context()`: добавить `has_sedentary` (есть ли доступный
  `CarGroup` с `CarType == 'Sedentary'`), `show_seat_group = has_sedentary`.
- `_berth_options(context)`: добавить `'together'`, когда `show_seat_group`.
- `_BERTH_BTN['together'] = "🔗 Мест рядом"`; `_BERTH_UNIT['together'] = "групп мест"`.
- `format_filter_summary(car_types, berth, max_price, min_seats=1)` — новый
  необязательный параметр (не ломает текущие вызовы); при `berth == 'together'`
  собирает `"{min_seats}+ мест рядом"` вместо статичной строки из `_BERTH_SUMMARY`.
- `build_filter_keyboard(...)`: новая строка «🔢 Мест: N (изменить)»
  (callback `flt_seats_set`), видима когда `context.get("show_seat_group")`.
  Без кнопки сброса — минимум всегда ≥ 1.

## UX (`handlers/search.py`)

- Новый шаг `search_step = 'await_seats'` и `handle_seats_input` — по образцу
  `handle_price_input`, но `max(1, int(digits))` (нет варианта «без лимита»).
- `handle_filter_toggle`: ветка `kind == 'seats' and value == 'set'` переводит
  в `await_seats` и просит ввод текстом (как `flt_price_set`).
- `_render_filter_panel`, `check_subscription_now`: в местах, где сейчас
  `if berth in SEATMAP_BERTHS: SeatMapService().count_for_berth(...)` —
  прокинуть `min_count=<min_seats>` (значение из `search_state`/`subscription`).
- `handle_edit_filters`/`save_subscription_filters`: без изменений в структуре —
  `min_seats` подписки уже читается/пишется, просто теперь реально меняется
  через панель.
- Все вызовы `format_filter_summary(...)` — передать `min_seats`.

## Мониторинг (`services/monitoring.py`)

`count_matched` и `format_availability_message`: там, где сейчас
`SeatMapService().count_for_berth/detail_for_berth(...)` вызывается при
`subscription.berth in SEATMAP_BERTHS`, добавить `min_count=subscription.min_seats`.
Для `cabin`/`pair` параметр не используется — поведение не меняется.
`_filtered_state`/дедуп-логика (`subscription_states`) не меняются: они уже
работают через `count_matched`, который просто начинает корректно считать и для
`'together'`.

## Обратная совместимость

Существующие подписки с `berth` ∈ `{any, lower, upper, side, cabin, pair}` и
`min_seats=1` (дефолт) продолжают работать без изменений в поведении. Новая
ветка активируется только явным выбором «🔗 Мест рядом» в панели.

## Тестирование

- `tests/test_seatmap.py`: `blocks_with_at_least`/`together_seats_detail` на
  фикстуре формы Sedentary (блоки переменного размера, как в реальном ответе
  для поезда 812С) — порог `min_count`, фильтрация по `car_types`/`max_price`,
  сортировка, отсутствие захвата `Compartment`/`ReservedSeat` при
  `include_types=("Sedentary",)`.
- `tests/test_filters.py`: `has_sedentary`/`show_seat_group` в контексте;
  `_berth_options` включает `'together'` только при наличии сидячих;
  `format_filter_summary` с `min_seats` для `berth='together'`; новая кнопка в
  `build_filter_keyboard`.
- `tests/test_monitoring_filters.py`: `count_matched` прокидывает `min_count`
  при `berth='together'`.
- Все новые тесты — юнит, не integration.

## Затрагиваемые файлы

- `services/rzd_seatmap.py` — `blocks_with_at_least`, `together_seats_detail`,
  `SEATMAP_BERTHS`, `min_count` в `detail_for_berth`/`count_for_berth`,
  `format_seat_groups`.
- `services/filters.py` — контекст, кнопка, единица счёта, сводка фильтра.
- `handlers/search.py` — шаг `await_seats`, `handle_seats_input`,
  прокидывание `min_count`, обновлённые вызовы `format_filter_summary`.
- `services/monitoring.py` — прокидывание `min_count` в `count_matched`/
  `format_availability_message`.
- `tests/` — новые/обновлённые юнит-тесты.
