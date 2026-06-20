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
    
    # Базовый адрес страницы покупки на сайте РЖД (для deep-link в уведомлениях)
    PURCHASE_BASE_URL = "https://ticket.rzd.ru/searchresults/v/1"

    def __init__(self, api_url: str = None, suggest_url: str = None, user_agent: str = None):
        # Параметры можно передать явно (удобно для тестов и переиспользования
        # сервиса вне бота), по умолчанию берутся из config.
        self.api_url = api_url or config.RZD_API_URL
        self.suggest_url = suggest_url or config.RZD_SUGGEST_URL
        self.user_agent = user_agent or config.USER_AGENT
    
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
    
    @staticmethod
    def _available_count(car_group: Dict) -> int:
        """Реальное число доступных мест в группе вагонов.

        У РЖД PlaceQuantity иногда равен 0, хотя места есть (динамическое
        ценообразование / продажа целыми купе) — настоящее количество лежит в
        TotalPlaceQuantity. Берём его, а PlaceQuantity — лишь запасной вариант.
        """
        tpq = car_group.get('TotalPlaceQuantity')
        if tpq is None:
            tpq = car_group.get('PlaceQuantity', 0)
        return tpq or 0

    def check_available_seats(self, train: Dict, min_seats: int = 1) -> bool:
        """Проверка наличия свободных мест в поезде"""
        try:
            for car_group in train.get('CarGroups', []):
                if (car_group.get('AvailabilityIndication') == 'Available' and
                    self._available_count(car_group) >= min_seats):
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
                    total_seats += self._available_count(car_group)
            return total_seats
        except Exception as e:
            logger.error(f"Ошибка подсчета мест в поезде: {e}")
            return 0
    
    @staticmethod
    def format_duration(minutes) -> str:
        """Форматирование длительности в пути (минуты -> 'Xч Yм')"""
        try:
            total = int(minutes)
        except (TypeError, ValueError):
            return ''
        if total <= 0:
            return ''
        hours, mins = divmod(total, 60)
        if hours and mins:
            return f"{hours}ч {mins}м"
        if hours:
            return f"{hours}ч"
        return f"{mins}м"

    def extract_train_info(self, train: Dict) -> Dict:
        """Извлекает отображаемые поля поезда из ответа API РЖД.

        API возвращает время в полях LocalDepartureDateTime/LocalArrivalDateTime
        и название в TrainName/TrainDescription — а не DepartureTime/RouteName.
        """
        def _time(value) -> str:
            if not value:
                return ''
            try:
                return datetime.fromisoformat(value).strftime('%H:%M')
            except (ValueError, TypeError):
                # Fallback: 'YYYY-MM-DDTHH:MM:SS' -> 'HH:MM'
                return value[11:16] if isinstance(value, str) and len(value) >= 16 else ''

        return {
            'number': train.get('TrainNumber') or train.get('DisplayTrainNumber') or 'N/A',
            'name': train.get('TrainName') or train.get('TrainDescription') or '',
            'departure': _time(train.get('LocalDepartureDateTime')),
            'arrival': _time(train.get('LocalArrivalDateTime')),
            'duration': self.format_duration(train.get('TripDuration')),
        }

    def count_seats_breakdown(self, train: Dict) -> Dict:
        """Разбивка свободных мест: всего / нижние / верхние и по типам вагонов"""
        result = {'total': 0, 'lower': 0, 'upper': 0, 'types': {}}
        try:
            for cg in train.get('CarGroups', []):
                if cg.get('AvailabilityIndication') != 'Available':
                    continue
                qty = self._available_count(cg)
                result['total'] += qty
                result['lower'] += cg.get('LowerPlaceQuantity', 0) or 0
                result['upper'] += cg.get('UpperPlaceQuantity', 0) or 0
                name = cg.get('CarTypeName') or cg.get('CarType') or '?'
                result['types'][name] = result['types'].get(name, 0) + qty
        except Exception as e:
            logger.error(f"Ошибка разбивки мест в поезде: {e}")
        return result

    def match_seats(self, train: Dict, car_types=None, berth: str = 'any',
                    max_price: int = 0) -> Dict:
        """Считает места, подходящие под фильтры подписки.

        car_types: коллекция кодов CarType (или None/пусто = любой).
        berth: 'any' | 'lower' | 'upper' | 'side' | 'cabin'
            low/верх — основные (не боковые), 'side' — боковые (LowerSide+UpperSide),
            'cabin' — полностью свободные купе (EmptyCabinQuantity).
        max_price: потолок цены в рублях (0 = любая), сравнение с MinPrice группы.
        """
        result = {'total': 0, 'lower': 0, 'upper': 0, 'side': 0, 'min_price': None, 'by_type': {}}
        wanted = set(car_types) if car_types else None
        try:
            for cg in train.get('CarGroups', []):
                if cg.get('AvailabilityIndication') != 'Available':
                    continue
                if wanted is not None and cg.get('CarType') not in wanted:
                    continue
                price = cg.get('MinPrice')
                if max_price and price and price > max_price:
                    continue
                main_lower = cg.get('LowerPlaceQuantity', 0) or 0
                main_upper = cg.get('UpperPlaceQuantity', 0) or 0
                side = (cg.get('LowerSidePlaceQuantity', 0) or 0) + (cg.get('UpperSidePlaceQuantity', 0) or 0)
                cabins = cg.get('EmptyCabinQuantity', 0) or 0
                # Сколько мест в группе подходит под выбранную категорию полки
                if berth == 'lower':
                    matched = main_lower
                elif berth == 'upper':
                    matched = main_upper
                elif berth == 'side':
                    matched = side
                elif berth == 'cabin':
                    matched = cabins
                else:
                    matched = self._available_count(cg)
                if matched <= 0:
                    continue
                result['total'] += matched
                result['lower'] += main_lower
                result['upper'] += main_upper
                result['side'] += side
                name = cg.get('CarTypeName') or cg.get('CarType') or '?'
                result['by_type'][name] = result['by_type'].get(name, 0) + matched
                if price and (result['min_price'] is None or price < result['min_price']):
                    result['min_price'] = price
        except Exception as e:
            logger.error(f"Ошибка match_seats: {e}")
        return result

    def min_price(self, train: Dict) -> Optional[float]:
        """Минимальная цена среди доступных вагонов (None, если мест нет)"""
        try:
            prices = [
                cg.get('MinPrice') for cg in train.get('CarGroups', [])
                if cg.get('AvailabilityIndication') == 'Available' and cg.get('MinPrice')
            ]
            return min(prices) if prices else None
        except Exception as e:
            logger.error(f"Ошибка определения цены поезда: {e}")
            return None

    def resolve_node_id(self, code: str, name: str = '') -> str:
        """Находит nodeId станции (для ссылки на поиск РЖД) по коду и имени.

        Страница поиска РЖД использует nodeId станции, а не экспресс-код. Suggest
        не ищет по числовому коду, поэтому запрашиваем по очищенному имени и
        сопоставляем по expressCode. Возвращает nodeId или '' если не нашли.
        """
        import re
        if not name:
            return ''
        query = re.sub(r'\s*\(\d+\)\s*$', '', name)      # убрать хвост "(2060001)"
        query = re.sub(r'\s*\(.*?\)', '', query).strip()  # убрать "(Московский вокзал)"
        candidates = [q for q in (query, query.split()[0] if query else '') if q]
        try:
            for q in candidates:
                for st in self.search_stations(q):
                    if str(st.get('expressCode')) == str(code):
                        return st.get('nodeId') or st.get('cityId') or ''
        except Exception as e:
            logger.error(f"Ошибка резолва nodeId для {code}: {e}")
        return ''

    def build_purchase_url(self, origin_code: str, destination_code: str,
                           departure_date: str, origin_name: str = '',
                           destination_name: str = '', adult: int = 1) -> str:
        """Формирует ссылку на страницу поиска РЖД.

        Сайт ждёт nodeId станций и дату 'YYYY-MM-DD'. nodeId резолвим по имени;
        если не удалось — откатываемся на экспресс-код (хуже, но не пусто).
        """
        try:
            date_part = datetime.fromisoformat(departure_date).strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            date_part = (departure_date or '')[:10]
        origin = self.resolve_node_id(origin_code, origin_name) or origin_code
        dest = self.resolve_node_id(destination_code, destination_name) or destination_code
        return f"{self.PURCHASE_BASE_URL}/{origin}/{dest}/{date_part}?adult={max(1, adult)}"

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
