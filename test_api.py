import requests
import json

def test_station_search():
    """Тестирование API поиска станций"""
    
    # URL для поиска станций
    suggest_url = "https://ticket.rzd.ru/api/v1/suggests"
    
    # Параметры запроса
    params = {
        'Query': 'москва',
        'TransportType': 'bus,avia,rail,aeroexpress,suburban,boat',
        'GroupResults': 'true',
        'RailwaySortPriority': 'true',
        'SynonymOn': '1',
        'Language': 'ru'
    }
    
    # Заголовки
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        print("🔍 Тестирование API поиска станций...")
        print(f"Запрос: {suggest_url}")
        print(f"Параметры: {params}")
        print("-" * 50)
        
        response = requests.get(suggest_url, params=params, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        print(f"✅ Статус ответа: {response.status_code}")
        # Обрабатываем разные типы результатов
        stations = []
        
        # Добавляем станции из разных категорий
        if data.get('train'):
            stations.extend(data['train'])
        if data.get('city'):
            stations.extend(data['city'])
        if data.get('avia'):
            stations.extend(data['avia'])
        
        print(f"📊 Найдено станций: {len(stations)}")
        print("\n🏁 Найденные станции:")
        
        for i, station in enumerate(stations[:5], 1):
            name = station.get('name', 'N/A')
            code = station.get('expressCode', 'N/A')
            print(f"{i}. {name} (код: {code})")
            
        print("\n📋 Полный ответ:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")

def test_train_search():
    """Тестирование API поиска поездов"""
    
    # URL для поиска поездов
    api_url = "https://ticket.rzd.ru/api/v1/railway-service/prices/train-pricing"
    
    # Параметры запроса (пример: Москва - Санкт-Петербург)
    params = {
        "service_provider": "B2B_RZD",
        "getByLocalTime": "true",
        "carGrouping": "DontGroup",
        "destination": "2060000",  # Санкт-Петербург
        "origin": "2060440",       # Москва
        "departureDate": "2025-01-15T00:00:00",
        "specialPlacesDemand": "StandardPlacesAndForDisabledPersons",
        "carIssuingType": "Passenger",
        "getTrainsFromSchedule": "true",
        "adultPassengersQuantity": 1,
        "childrenPassengersQuantity": 0,
        "hasPlacesForLargeFamily": "false"
    }
    
    # Заголовки
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        print("\n🚆 Тестирование API поиска поездов...")
        print(f"Запрос: {api_url}")
        print(f"Маршрут: Москва → Санкт-Петербург")
        print(f"Дата: 2025-01-15")
        print("-" * 50)
        
        response = requests.get(api_url, params=params, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        print(f"✅ Статус ответа: {response.status_code}")
        print(f"🚂 Найдено поездов: {len(data.get('Trains', []))}")
        
        if data.get('Trains'):
            print("\n📋 Информация о поездах:")
            for i, train in enumerate(data['Trains'][:3], 1):
                train_number = train.get('TrainNumber', 'N/A')
                route_name = train.get('RouteName', '')
                departure_time = train.get('DepartureTime', '')
                arrival_time = train.get('ArrivalTime', '')
                
                print(f"{i}. Поезд {train_number}")
                print(f"   Маршрут: {route_name}")
                print(f"   Время: {departure_time} → {arrival_time}")
                
                # Считаем доступные места
                available_seats = 0
                for car_group in train.get('CarGroups', []):
                    if car_group.get('AvailabilityIndication') == 'Available':
                        available_seats += car_group.get('PlaceQuantity', 0)
                
                print(f"   Доступно мест: {available_seats}")
                print()
        else:
            print("❌ Поезда не найдены")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка запроса: {e}")
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")

if __name__ == "__main__":
    print("🧪 Тестирование API РЖД")
    print("=" * 50)
    
    # Тестируем поиск станций
    test_station_search()
    
    # Тестируем поиск поездов
    test_train_search()
    
    print("\n✅ Тестирование завершено!")
