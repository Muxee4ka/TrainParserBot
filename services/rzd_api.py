"""
Сервис для работы с API РЖД
"""
import requests
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime

from config import config

logger = logging.getLogger(__name__)


class RZDAPIService:
    """Сервис для работы с API РЖД"""
    
    def __init__(self):
        self.api_url = config.RZD_API_URL
        self.suggest_url = config.RZD_SUGGEST_URL
        self.user_agent = config.USER_AGENT
    
    def search_stations(self, query: str) -> List[Dict]:
        """Поиск станций по запросу"""
        try:
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'ru-RU,ru;q=0.9',
                'User-Agent': self.user_agent,
            }
            
            params = {
                'Query': query,
                'TransportType': 'bus,avia,rail,aeroexpress,suburban,boat',
                'GroupResults': 'true',
                'RailwaySortPriority': 'true',
                'SynonymOn': '1',
                'Language': 'ru'
            }
            
            response = requests.get(
                self.suggest_url, 
                params=params, 
                headers=headers, 
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Обрабатываем разные типы результатов
            stations = []
            
            # Добавляем станции из разных категорий
            if data.get('train'):
                stations.extend(data['train'])
            if data.get('city'):
                stations.extend(data['city'])
            if data.get('avia'):
                stations.extend(data['avia'])
            
            logger.info(f"Найдено {len(stations)} станций для запроса '{query}'")
            return stations[:config.MAX_STATIONS_PER_SEARCH]
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к API станций: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON ответа: {e}")
            return []
        except Exception as e:
            logger.error(f"Неожиданная ошибка при поиске станций: {e}")
            return []
    
    def search_trains(self, origin_code: str, destination_code: str, 
                     departure_date: str, adult_passengers: int = 1, 
                     children_passengers: int = 0) -> Dict:
        """Поиск поездов"""
        try:
            params = {
                "service_provider": "B2B_RZD",
                "getByLocalTime": "true",
                "carGrouping": "DontGroup",
                "destination": destination_code,
                "origin": origin_code,
                "departureDate": departure_date,
                "specialPlacesDemand": "StandardPlacesAndForDisabledPersons",
                "carIssuingType": "Passenger",
                "getTrainsFromSchedule": "true",
                "adultPassengersQuantity": adult_passengers,
                "childrenPassengersQuantity": children_passengers,
                "hasPlacesForLargeFamily": "false"
            }
            
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'ru-RU,ru;q=0.9',
                'User-Agent': self.user_agent,
            }
            
            response = requests.get(
                self.api_url, 
                params=params, 
                headers=headers, 
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            trains = data.get('Trains', [])
            logger.info(f"Найдено {len(trains)} поездов для маршрута {origin_code} -> {destination_code}")
            
            return {
                'trains': trains[:config.MAX_TRAINS_PER_RESULT],
                'total_count': len(trains)
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к API поездов: {e}")
            return {'trains': [], 'total_count': 0}
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON ответа: {e}")
            return {'trains': [], 'total_count': 0}
        except Exception as e:
            logger.error(f"Неожиданная ошибка при поиске поездов: {e}")
            return {'trains': [], 'total_count': 0}
    
    def check_available_seats(self, train: Dict, min_seats: int = 1) -> bool:
        """Проверка наличия свободных мест в поезде"""
        try:
            for car_group in train.get('CarGroups', []):
                if (car_group.get('AvailabilityIndication') == 'Available' and
                    car_group.get('PlaceQuantity', 0) >= min_seats):
                    return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки мест в поезде: {e}")
            return False
    
    def count_available_seats(self, train: Dict) -> int:
        """Подсчет общего количества свободных мест в поезде"""
        try:
            total_seats = 0
            for car_group in train.get('CarGroups', []):
                if car_group.get('AvailabilityIndication') == 'Available':
                    total_seats += car_group.get('PlaceQuantity', 0)
            return total_seats
        except Exception as e:
            logger.error(f"Ошибка подсчета мест в поезде: {e}")
            return 0
    
    def format_station_name(self, station: Dict) -> str:
        """Форматирование названия станции для отображения"""
        name = station.get('name', '')
        code = station.get('expressCode', '')
        return f"{name} ({code})" if name and code else name or code
    
    def create_safe_callback_data(self, station: Dict) -> str:
        """Создание безопасного callback_data для кнопки"""
        try:
            station_name = station.get('name', '')
            station_code = station.get('expressCode', '')
            
            if not station_name or not station_code:
                return f"station_{station_code}"
            
            # Очищаем название станции от специальных символов и ограничиваем длину
            clean_name = station_name.replace('(', '').replace(')', '').replace('-', ' ').replace('_', ' ')
            clean_name = clean_name[:30]  # Ограничиваем длину
            
            # Создаем безопасный callback_data
            callback_data = f"station_{station_code}_{clean_name}"
            
            # Проверяем длину callback_data (лимит Telegram - 64 байта)
            if len(callback_data.encode('utf-8')) <= config.MAX_CALLBACK_DATA_LENGTH:
                return callback_data
            else:
                # Если слишком длинный, используем только код
                return f"station_{station_code}"
                
        except Exception as e:
            logger.error(f"Ошибка создания callback_data: {e}")
            return f"station_{station.get('expressCode', '')}"
