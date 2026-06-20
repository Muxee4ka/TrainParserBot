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
    assert f.format_filter_summary("ReservedSeat", "side", 0) == "Плац · боковое"
    assert f.format_filter_summary("Compartment", "cabin", 0) == "Купе · купе целиком"

def test_matched_unit():
    assert f.matched_unit("cabin") == "пустых купе"
    assert f.matched_unit("lower") == "мест"
    assert f.matched_unit("any") == "мест"

def test_build_filter_keyboard_marks_selected():
    kb = f.build_filter_keyboard("Compartment", "lower", 5000)
    flat = [b for row in kb for b in row]
    texts = {b["text"]: b["callback_data"] for b in flat}
    assert "✅ Купе" in texts and texts["✅ Купе"] == "flt_car_Compartment"
    assert "✅ Нижнее" in texts and texts["✅ Нижнее"] == "flt_berth_lower"
    assert "✅ ≤5000" in texts
    # все опции полки присутствуют, каждая своей строкой
    berth_cbs = {b["callback_data"] for row in kb for b in row if b["callback_data"].startswith("flt_berth_")}
    assert berth_cbs == {"flt_berth_any", "flt_berth_lower", "flt_berth_upper", "flt_berth_side", "flt_berth_cabin"}
    sub_btn = next(b for b in flat if b["callback_data"] == "subscribe_filtered")
    assert sub_btn["style"] == "primary"

def test_selected_buttons_have_success_style():
    kb = f.build_filter_keyboard("Compartment", "lower", 5000)
    flat = [b for row in kb for b in row]
    by_cb = {b["callback_data"]: b for b in flat}
    # выбранные подсвечены success, невыбранные — без style
    assert by_cb["flt_car_Compartment"].get("style") == "success"
    assert by_cb["flt_berth_lower"].get("style") == "success"
    assert by_cb["flt_price_5000"].get("style") == "success"
    assert "style" not in by_cb["flt_car_ReservedSeat"]
    assert "style" not in by_cb["flt_berth_upper"]

def test_cabin_option_selected():
    kb = f.build_filter_keyboard("", "cabin", 0)
    texts = [b["text"] for row in kb for b in row]
    assert "✅ 🚪 Купе целиком" in texts
