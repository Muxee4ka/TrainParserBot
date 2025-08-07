#!/usr/bin/env python3
"""
Тестовый скрипт для проверки callback_data кнопок
"""

def test_callback_data_validation():
    """Тест валидации callback_data"""
    print("🔍 Тестирование callback_data кнопок...")
    
    # Тестовые данные станций
    test_stations = [
        {"name": "Москва Казанская (Казанский вокзал)", "expressCode": "2000003"},
        {"name": "Санкт-Петербург-Главный (Московский вокзал)", "expressCode": "2004001"},
        {"name": "Казань Пасс", "expressCode": "2060500"},
        {"name": "Очень длинное название станции с множеством символов и пробелов", "expressCode": "1234567"},
        {"name": "Станция с символами: ()-_,.!@#$%", "expressCode": "9999999"}
    ]
    
    for i, station in enumerate(test_stations, 1):
        station_name = station.get('name', '')
        station_code = station.get('expressCode', '')
        
        print(f"\n{i}. Тестируем станцию: {station_name}")
        
        # Очищаем название станции от специальных символов и ограничиваем длину
        clean_name = station_name.replace('(', '').replace(')', '').replace('-', ' ').replace('_', ' ')
        clean_name = clean_name[:30]  # Ограничиваем длину
        
        # Создаем безопасный callback_data
        callback_data = f"station_{station_code}_{clean_name}"
        
        # Проверяем длину callback_data (лимит Telegram - 64 байта)
        callback_bytes = len(callback_data.encode('utf-8'))
        
        print(f"   Оригинальное название: {station_name}")
        print(f"   Очищенное название: {clean_name}")
        print(f"   Callback data: {callback_data}")
        print(f"   Размер в байтах: {callback_bytes}")
        
        if callback_bytes <= 64:
            print(f"   ✅ Валидный callback_data")
        else:
            # Если слишком длинный, используем только код
            fallback_callback = f"station_{station_code}"
            fallback_bytes = len(fallback_callback.encode('utf-8'))
            print(f"   ❌ Слишком длинный, используем fallback: {fallback_callback}")
            print(f"   Fallback размер в байтах: {fallback_bytes}")
            
            if fallback_bytes <= 64:
                print(f"   ✅ Fallback валидный")
            else:
                print(f"   ❌ Fallback тоже слишком длинный!")

def test_callback_data_parsing():
    """Тест парсинга callback_data"""
    print("\n🔍 Тестирование парсинга callback_data...")
    
    test_callbacks = [
        "station_2000003_Москва Казанская",
        "station_2004001_Санкт-Петербург-Главный",
        "station_2060500_Казань Пасс",
        "station_1234567",  # Только код
        "invalid_format",
        "station_",  # Неполный
    ]
    
    for callback in test_callbacks:
        print(f"\nТестируем callback: {callback}")
        
        try:
            if callback.startswith("station_"):
                parts = callback.split("_", 2)
                if len(parts) >= 2:
                    station_code = parts[1]
                    station_name = parts[2] if len(parts) > 2 else station_code
                    print(f"   ✅ Успешно распарсено:")
                    print(f"      Код: {station_code}")
                    print(f"      Название: {station_name}")
                else:
                    print(f"   ❌ Неверный формат: недостаточно частей")
            else:
                print(f"   ❌ Неверный формат: не начинается с 'station_'")
        except Exception as e:
            print(f"   ❌ Ошибка при парсинге: {e}")

if __name__ == "__main__":
    print("🧪 Тестирование callback_data")
    print("=" * 50)
    
    test_callback_data_validation()
    test_callback_data_parsing()
    
    print("\n✅ Тестирование завершено!")



