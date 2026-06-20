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
