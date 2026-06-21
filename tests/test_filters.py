from services import filters as f


def _berth_cargroups():
    # купейный + плацкартный поезд
    return [
        {"AvailabilityIndication": "Available", "CarType": "Compartment", "CarTypeName": "Купе",
         "MinPrice": 3000, "MaxPrice": 5000},
        {"AvailabilityIndication": "Available", "CarType": "ReservedSeat", "CarTypeName": "Плац",
         "MinPrice": 1800, "MaxPrice": 2600},
    ]


def _seated_cargroups():
    # сидячий поезд (Сапсан): один CarType, разные классы
    return [
        {"AvailabilityIndication": "Available", "CarType": "Sedentary", "CarTypeName": "СИД",
         "ServiceClassNameRu": "Эконом+", "MinPrice": 10000, "MaxPrice": 16000},
        {"AvailabilityIndication": "Available", "CarType": "Sedentary", "CarTypeName": "СИД",
         "ServiceClassNameRu": "Бизнес класс", "MinPrice": 20000, "MaxPrice": 40000},
    ]


def test_toggle_car_type_add_remove():
    assert f.toggle_car_type("", "Compartment") == "Compartment"
    assert f.toggle_car_type("Compartment", "ReservedSeat") == "Compartment,ReservedSeat"
    assert f.toggle_car_type("Compartment,ReservedSeat", "Compartment") == "ReservedSeat"
    # произвольный токен (класс обслуживания) не теряется
    assert f.toggle_car_type("", "Бизнес класс") == "Бизнес класс"


def test_parse_filter_callback():
    assert f.parse_filter_callback("flt_car_Compartment") == ("car", "Compartment")
    assert f.parse_filter_callback("flt_berth_lower") == ("berth", "lower")
    assert f.parse_filter_callback("flt_price_set") == ("price", "set")
    assert f.parse_filter_callback("subscribe_filtered") is None


def test_format_filter_summary():
    assert f.format_filter_summary("", "any", 0) == "любые места"
    assert f.format_filter_summary("Compartment", "lower", 8000) == "Купе · нижнее · до 8000 ₽"
    assert f.format_filter_summary("Бизнес класс", "any", 0) == "Бизнес класс"


def test_matched_unit():
    assert f.matched_unit("cabin") == "пустых купе"
    assert f.matched_unit("pair") == "купе с парой низ+верх"
    assert f.matched_unit("any") == "мест"


def test_build_filter_context_berth_train():
    ctx = f.build_filter_context(_berth_cargroups())
    assert [c["value"] for c in ctx["categories"]] == ["Compartment", "ReservedSeat"]
    assert ctx["has_berths"] is True and ctx["show_side"] is True and ctx["show_cabin_pair"] is True
    assert ctx["price_min"] == 1800 and ctx["price_max"] == 5000


def test_build_filter_context_seated_train():
    ctx = f.build_filter_context(_seated_cargroups())
    # категории = классы обслуживания, рядов полки нет
    assert [c["label"] for c in ctx["categories"]] == ["Эконом+", "Бизнес класс"]
    assert ctx["has_berths"] is False
    assert ctx["price_min"] == 10000 and ctx["price_max"] == 40000


def test_seated_keyboard_has_classes_no_berths():
    ctx = f.build_filter_context(_seated_cargroups())
    kb = f.build_filter_keyboard("", "any", 0, ctx)
    cbs = [b["callback_data"] for row in kb for b in row]
    assert "flt_car_Эконом+" in cbs
    assert not any(c.startswith("flt_berth_") for c in cbs)  # полок нет у сидячих
    assert "flt_price_set" in cbs  # ввод цены вручную


def test_berth_keyboard_has_berths_and_price_set():
    ctx = f.build_filter_context(_berth_cargroups())
    kb = f.build_filter_keyboard("Compartment", "lower", 0, ctx)
    flat = [b for row in kb for b in row]
    by_cb = {b["callback_data"]: b for b in flat}
    assert by_cb["flt_car_Compartment"].get("style") == "success"
    assert by_cb["flt_berth_lower"].get("style") == "success"
    assert "flt_berth_cabin" in by_cb and "flt_berth_pair" in by_cb and "flt_berth_side" in by_cb
    # цена — кнопка ручного ввода; «Сброс» появляется только при заданном лимите
    assert "flt_price_set" in by_cb
    assert "flt_price_0" not in by_cb


def test_price_reset_button_appears_when_capped():
    ctx = f.build_filter_context(_berth_cargroups())
    kb = f.build_filter_keyboard("", "any", 3000, ctx)
    cbs = [b["callback_data"] for row in kb for b in row]
    assert "flt_price_set" in cbs and "flt_price_0" in cbs
