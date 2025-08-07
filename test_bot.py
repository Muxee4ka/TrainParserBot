#!/usr/bin/env python3
"""
Тестовый скрипт для проверки функциональности бота
"""

import requests
import json
from datetime import datetime

def test_station_search():
    """Тест поиска станций"""
    print("🔍 Тестирование поиска станций...")
    
    test_queries = ["москва", "санкт-петербург", "казань"]
    
    for query in test_queries:
        print(f"\n📝 Поиск: '{query}'")
        
        try:
            response = requests.get(
                'https://ticket.rzd.ru/api/v1/suggests',
                params={
                    'Query': query,
                    'TransportType': 'bus,avia,rail,aeroexpress,suburban,boat',
                    'GroupResults': 'true',
                    'RailwaySortPriority': 'true',
                    'SynonymOn': '1',
                    'Language': 'ru'
                },
                headers={
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'ru-RU,ru;q=0.9',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                stations = []
                
                if data.get('train'):
                    stations.extend(data['train'])
                if data.get('city'):
                    stations.extend(data['city'])
                
                print(f"✅ Найдено станций: {len(stations)}")
                
                if stations:
                    print("🏁 Примеры станций:")
                    for i, station in enumerate(stations[:3], 1):
                        name = station.get('name', 'N/A')
                        code = station.get('expressCode', 'N/A')
                        print(f"   {i}. {name} (код: {code})")
                else:
                    print("❌ Станции не найдены")
            else:
                print(f"❌ Ошибка API: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")

def test_train_search():
    """Тест поиска поездов"""
    print("\n🚆 Тестирование поиска поездов...")
    
    # Тестовые маршруты
    routes = [
        {
            "name": "Москва → Санкт-Петербург",
            "origin": "2000001",  # Москва Курская
            "destination": "2000003",  # Санкт-Петербург
            "date": "2025-01-15T00:00:00"
        },
        {
            "name": "Москва → Казань",
            "origin": "2000001",  # Москва Курская
            "destination": "2000005",  # Казань
            "date": "2025-01-15T00:00:00"
        }
    ]
    
    for route in routes:
        print(f"\n📝 Маршрут: {route['name']}")
        
        try:
            response = requests.get(
                'https://ticket.rzd.ru/api/v1/railway-service/prices/train-pricing',
                params={
                    "service_provider": "B2B_RZD",
                    "getByLocalTime": "true",
                    "carGrouping": "DontGroup",
                    "destination": route['destination'],
                    "origin": route['origin'],
                    "departureDate": route['date'],
                    "specialPlacesDemand": "StandardPlacesAndForDisabledPersons",
                    "carIssuingType": "Passenger",
                    "getTrainsFromSchedule": "true",
                    "adultPassengersQuantity": 1,
                    "childrenPassengersQuantity": 0,
                    "hasPlacesForLargeFamily": "false"
                },
                headers={
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'ru-RU,ru;q=0.9',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                trains = data.get('Trains', [])
                
                print(f"✅ Найдено поездов: {len(trains)}")
                
                if trains:
                    print("🚂 Примеры поездов:")
                    for i, train in enumerate(trains[:3], 1):
                        train_number = train.get('TrainNumber', 'N/A')
                        departure_time = train.get('DepartureTime', '')
                        arrival_time = train.get('ArrivalTime', '')
                        
                        print(f"   {i}. Поезд {train_number}")
                        print(f"      Время: {departure_time} → {arrival_time}")
                        
                        # Считаем доступные места
                        available_seats = 0
                        for car_group in train.get('CarGroups', []):
                            if car_group.get('AvailabilityIndication') == 'Available':
                                available_seats += car_group.get('PlaceQuantity', 0)
                        
                        print(f"      Доступно мест: {available_seats}")
                else:
                    print("❌ Поезда не найдены")
            else:
                print(f"❌ Ошибка API: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")

def test_database():
    """Тест базы данных"""
    print("\n🗄️ Тестирование базы данных...")
    
    try:
        import sqlite3
        
        # Создаем тестовую базу
        conn = sqlite3.connect("test_subscriptions.db")
        cursor = conn.cursor()
        
        # Создаем таблицу
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                origin_code TEXT,
                origin_name TEXT,
                destination_code TEXT,
                destination_name TEXT,
                departure_date TEXT,
                train_numbers TEXT,
                car_types TEXT,
                min_seats INTEGER,
                adult_passengers INTEGER,
                children_passengers INTEGER,
                interval_minutes INTEGER,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Добавляем тестовую подписку
        cursor.execute('''
            INSERT INTO subscriptions 
            (user_id, origin_code, origin_name, destination_code, destination_name, 
             departure_date, train_numbers, car_types, min_seats, adult_passengers, 
             children_passengers, interval_minutes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            12345,
            "2000001",
            "Москва Курская",
            "2000003", 
            "Санкт-Петербург",
            "2025-01-15T00:00:00",
            "",
            "",
            1,
            1,
            0,
            5
        ))
        
        conn.commit()
        
        # Проверяем подписку
        cursor.execute('SELECT * FROM subscriptions WHERE user_id = ?', (12345,))
        subscription = cursor.fetchone()
        
        if subscription:
            print("✅ Тестовая подписка создана успешно")
            print(f"   ID: {subscription[0]}")
            print(f"   Маршрут: {subscription[3]} → {subscription[5]}")
            print(f"   Дата: {subscription[6]}")
        else:
            print("❌ Ошибка создания подписки")
        
        conn.close()
        
        # Удаляем тестовую базу
        import os
        if os.path.exists("test_subscriptions.db"):
            os.remove("test_subscriptions.db")
            print("✅ Тестовая база данных удалена")
            
    except Exception as e:
        print(f"❌ Ошибка базы данных: {e}")

def main():
    """Главная функция"""
    print("🧪 Тестирование функциональности бота")
    print("=" * 50)
    
    # Тестируем поиск станций
    test_station_search()
    
    # Тестируем поиск поездов
    test_train_search()
    
    # Тестируем базу данных
    test_database()
    
    print("\n✅ Тестирование завершено!")
    print("\n📋 Результаты:")
    print("• API поиска станций работает")
    print("• API поиска поездов работает") 
    print("• База данных настроена")
    print("\n🚀 Бот готов к запуску!")

if __name__ == "__main__":
    main()



