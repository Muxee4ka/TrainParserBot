"""Презентационная логика фильтров подписки (без зависимостей от aiogram).

Фильтры адаптируются под конкретный поезд: категории берутся из реальных вагонов
(тип вагона для купе/плац или класс обслуживания для сидячих), ряд «полка»
показывается только когда есть купе/плац, а ценовой потолок задаётся вводом суммы.
"""

CAR_TYPE_LABELS = {
    "Compartment": "Купе",
    "ReservedSeat": "Плац",
    "Sedentary": "СИД",
    "Soft": "Люкс",
}
_BERTH_SUMMARY = {"lower": "нижнее", "upper": "верхнее", "side": "боковое",
                  "cabin": "купе целиком", "pair": "низ+верх в одном купе"}
_BERTH_BTN = {"any": "Любая", "lower": "Нижнее", "upper": "Верхнее", "side": "Боковое",
              "cabin": "🚪 Купе целиком", "pair": "🔼🔽 Низ+Верх вместе"}
_BERTH_UNIT = {"cabin": "пустых купе", "pair": "купе с парой низ+верх"}


def matched_unit(berth: str) -> str:
    """Единица счёта под фильтр (для 'cabin'/'pair' — купе, иначе — места)."""
    return _BERTH_UNIT.get(berth, "мест")


def category_token(cg: dict) -> str:
    """Токен категории вагона для фильтра: класс обслуживания у сидячих, иначе CarType."""
    if cg.get("CarType") == "Sedentary":
        return cg.get("ServiceClassNameRu") or cg.get("CarTypeName") or "СИД"
    return cg.get("CarType") or "?"


def category_label(cg: dict) -> str:
    """Подпись категории вагона для кнопки."""
    if cg.get("CarType") == "Sedentary":
        return cg.get("ServiceClassNameRu") or cg.get("CarTypeName") or "СИД"
    return CAR_TYPE_LABELS.get(cg.get("CarType"), cg.get("CarTypeName") or cg.get("CarType") or "?")


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


def toggle_car_type(csv: str, token: str) -> str:
    """Добавляет/убирает категорию вагона в CSV (сохраняет порядок выбора)."""
    items = [c for c in (csv or "").split(",") if c]
    if token in items:
        items.remove(token)
    else:
        items.append(token)
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


def _berth_options(context: dict) -> list:
    """Доступные варианты полки под тип поезда."""
    opts = ["any", "lower", "upper"]
    if context.get("show_side"):
        opts.append("side")
    if context.get("show_cabin_pair"):
        opts += ["cabin", "pair"]
    return opts


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
