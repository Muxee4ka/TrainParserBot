"""Пресеты и презентационная логика фильтров подписки (без зависимостей от aiogram)."""

CAR_TYPE_LABELS = {
    "Compartment": "Купе",
    "ReservedSeat": "Плац",
    "Sedentary": "СИД",
    "Soft": "Люкс",
}
CAR_TYPE_ORDER = ["Compartment", "ReservedSeat", "Sedentary", "Soft"]
PRICE_PRESETS = [3000, 5000, 8000]
_BERTH_SUMMARY = {"lower": "нижнее", "upper": "верхнее", "side": "боковое",
                  "cabin": "купе целиком", "pair": "низ+верх в одном купе"}
_BERTH_BTN = {"any": "Любая", "lower": "Нижнее", "upper": "Верхнее", "side": "Боковое",
              "cabin": "🚪 Купе целиком", "pair": "🔼🔽 Низ+Верх вместе"}
# Порядок кнопок полки (по одной в ряд: низ над верхом)
_BERTH_ORDER = ["any", "lower", "upper", "side", "cabin", "pair"]
_BERTH_UNIT = {"cabin": "пустых купе", "pair": "купе с парой низ+верх"}


def matched_unit(berth: str) -> str:
    """Единица счёта под фильтр (для 'cabin'/'pair' — купе, иначе — места)."""
    return _BERTH_UNIT.get(berth, "мест")


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


def _btn(text: str, callback_data: str, selected: bool = False) -> dict:
    """Кнопка фильтра; выбранная подсвечивается зелёным (Bot API 9.4 style)."""
    b = {"text": f"✅ {text}" if selected else text, "callback_data": callback_data}
    if selected:
        b["style"] = "success"
    return b


def build_filter_keyboard(car_types: str, berth: str, max_price: int,
                          submit_text: str = "🔔 Подписаться",
                          submit_cb: str = "subscribe_filtered") -> list:
    """Inline-клавиатура тогглов фильтров. submit_* задаёт нижнюю кнопку
    (подписка при создании или сохранение при правке существующей подписки)."""
    codes = set(c for c in (car_types or "").split(",") if c)

    car_row = [_btn(CAR_TYPE_LABELS[code], f"flt_car_{code}", code in codes) for code in CAR_TYPE_ORDER]

    # Полка — по одной кнопке в ряд (низ над верхом)
    berth_rows = [[_btn(_BERTH_BTN[val], f"flt_berth_{val}", berth == val)] for val in _BERTH_ORDER]

    price_row = [_btn(f"≤{p}", f"flt_price_{p}", max_price == p) for p in PRICE_PRESETS]
    price_row.append(_btn("Любая", "flt_price_0", not max_price))

    return [
        car_row,
        *berth_rows,
        price_row,
        [{"text": submit_text, "callback_data": submit_cb, "style": "primary"}],
    ]
