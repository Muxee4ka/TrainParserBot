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
