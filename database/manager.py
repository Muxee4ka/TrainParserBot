"""
Менеджер базы данных
"""
import sqlite3
import logging
from typing import List, Optional
from datetime import datetime

from .models import Subscription, SearchState
from config import config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер базы данных"""
    
    def __init__(self):
        self.db_path = config.DATABASE_PATH
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Создаем таблицу подписок
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
            
            # Создаем таблицу состояний поиска
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_states (
                    user_id INTEGER PRIMARY KEY,
                    origin_code TEXT,
                    origin_name TEXT,
                    destination_code TEXT,
                    destination_name TEXT,
                    departure_date TEXT,
                    adult_passengers INTEGER DEFAULT 1,
                    children_passengers INTEGER DEFAULT 0,
                    min_seats INTEGER DEFAULT 1,
                    train_numbers TEXT DEFAULT '',
                    car_types TEXT DEFAULT '',
                    progress_message_id INTEGER,
                    selected_train_number TEXT,
                    selected_train_info TEXT,
                    search_step TEXT DEFAULT 'origin',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    messages_to_delete TEXT DEFAULT ''
                )
            ''')

            # Таблица для хранения последнего состояния доступности мест по подписке
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscription_states (
                    subscription_id INTEGER PRIMARY KEY,
                    last_state TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Миграция: добавить колонку messages_to_delete, если её нет (для старых БД)
            try:
                cursor.execute("PRAGMA table_info(search_states)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'messages_to_delete' not in columns:
                    cursor.execute("ALTER TABLE search_states ADD COLUMN messages_to_delete TEXT DEFAULT ''")
                    logger.info("Добавлена колонка messages_to_delete в search_states")
            except Exception as mig_e:
                logger.error(f"Ошибка миграции search_states.messages_to_delete: {mig_e}")
            
            conn.commit()
            logger.info("База данных инициализирована")
            
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
            raise
        finally:
            conn.close()
    
    def create_subscription(self, subscription: Subscription) -> Optional[int]:
        """Создание новой подписки"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO subscriptions 
                (user_id, origin_code, origin_name, destination_code, destination_name, 
                 departure_date, train_numbers, car_types, min_seats, adult_passengers, 
                 children_passengers, interval_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                subscription.user_id,
                subscription.origin_code,
                subscription.origin_name,
                subscription.destination_code,
                subscription.destination_name,
                subscription.departure_date,
                subscription.train_numbers,
                subscription.car_types,
                subscription.min_seats,
                subscription.adult_passengers,
                subscription.children_passengers,
                subscription.interval_minutes
            ))
            
            subscription_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Создана подписка #{subscription_id} для пользователя {subscription.user_id}")
            return subscription_id
            
        except Exception as e:
            logger.error(f"Ошибка создания подписки: {e}")
            return None
        finally:
            conn.close()
    
    def get_user_subscriptions(self, user_id: int) -> List[Subscription]:
        """Получение подписок пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, user_id, origin_code, origin_name, destination_code, destination_name,
                       departure_date, train_numbers, car_types, min_seats, adult_passengers,
                       children_passengers, interval_minutes, is_active, created_at
                FROM subscriptions 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,))
            
            rows = cursor.fetchall()
            subscriptions = []
            
            for row in rows:
                subscription = Subscription(
                    id=row[0],
                    user_id=row[1],
                    origin_code=row[2],
                    origin_name=row[3],
                    destination_code=row[4],
                    destination_name=row[5],
                    departure_date=row[6],
                    train_numbers=row[7],
                    car_types=row[8],
                    min_seats=row[9],
                    adult_passengers=row[10],
                    children_passengers=row[11],
                    interval_minutes=row[12],
                    is_active=bool(row[13]),
                    created_at=datetime.fromisoformat(row[14])
                )
                subscriptions.append(subscription)
            
            return subscriptions
            
        except Exception as e:
            logger.error(f"Ошибка получения подписок: {e}")
            return []
        finally:
            conn.close()
    
    def get_active_subscriptions(self) -> List[Subscription]:
        """Получение всех активных подписок"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, user_id, origin_code, origin_name, destination_code, destination_name,
                       departure_date, train_numbers, car_types, min_seats, adult_passengers,
                       children_passengers, interval_minutes, is_active, created_at
                FROM subscriptions 
                WHERE is_active = 1
            ''')
            
            rows = cursor.fetchall()
            subscriptions = []
            
            for row in rows:
                subscription = Subscription(
                    id=row[0],
                    user_id=row[1],
                    origin_code=row[2],
                    origin_name=row[3],
                    destination_code=row[4],
                    destination_name=row[5],
                    departure_date=row[6],
                    train_numbers=row[7],
                    car_types=row[8],
                    min_seats=row[9],
                    adult_passengers=row[10],
                    children_passengers=row[11],
                    interval_minutes=row[12],
                    is_active=bool(row[13]),
                    created_at=datetime.fromisoformat(row[14])
                )
                subscriptions.append(subscription)
            
            return subscriptions
            
        except Exception as e:
            logger.error(f"Ошибка получения активных подписок: {e}")
            return []
        finally:
            conn.close()
    
    def disable_subscription(self, subscription_id: int, user_id: int) -> bool:
        """Отключение подписки"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE subscriptions 
                SET is_active = 0 
                WHERE id = ? AND user_id = ?
            ''', (subscription_id, user_id))
            
            success = cursor.rowcount > 0
            conn.commit()
            
            if success:
                logger.info(f"Подписка #{subscription_id} отключена")
            
            return success
            
        except Exception as e:
            logger.error(f"Ошибка отключения подписки: {e}")
            return False
        finally:
            conn.close()

    def enable_subscription(self, subscription_id: int, user_id: int) -> bool:
        """Включение ранее отключенной подписки"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE subscriptions
                SET is_active = 1
                WHERE id = ? AND user_id = ?
            ''', (subscription_id, user_id))

            success = cursor.rowcount > 0
            conn.commit()

            if success:
                logger.info(f"Подписка #{subscription_id} включена")

            return success

        except Exception as e:
            logger.error(f"Ошибка включения подписки: {e}")
            return False
        finally:
            conn.close()

    def get_subscription_last_state(self, subscription_id: int) -> Optional[str]:
        """Возвращает сохранённое состояние доступности мест по подписке"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT last_state FROM subscription_states WHERE subscription_id = ?
            ''', (subscription_id,))
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Ошибка получения состояния подписки {subscription_id}: {e}")
            return None
        finally:
            conn.close()

    def save_subscription_last_state(self, subscription_id: int, state: str) -> bool:
        """Сохраняет текущее состояние доступности мест по подписке"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE subscription_states
                SET last_state = ?, updated_at = CURRENT_TIMESTAMP
                WHERE subscription_id = ?
            ''', (state, subscription_id))
            if cursor.rowcount == 0:
                cursor.execute('''
                    INSERT INTO subscription_states (subscription_id, last_state)
                    VALUES (?, ?)
                ''', (subscription_id, state))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния подписки {subscription_id}: {e}")
            return False
        finally:
            conn.close()
    
    def save_search_state(self, search_state: SearchState):
        """Сохранение состояния поиска (с учетом новых полей)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            messages_to_delete_str = ','.join(str(mid) for mid in getattr(search_state, 'messages_to_delete', []))
            cursor.execute('''
                INSERT OR REPLACE INTO search_states 
                (user_id, origin_code, origin_name, destination_code, destination_name,
                 departure_date, adult_passengers, children_passengers, min_seats,
                 train_numbers, car_types, progress_message_id, selected_train_number, selected_train_info, search_step, updated_at, messages_to_delete)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                search_state.user_id,
                search_state.origin_code,
                search_state.origin_name,
                search_state.destination_code,
                search_state.destination_name,
                search_state.departure_date,
                search_state.adult_passengers,
                search_state.children_passengers,
                search_state.min_seats,
                search_state.train_numbers,
                search_state.car_types,
                search_state.progress_message_id,
                search_state.selected_train_number,
                search_state.selected_train_info,
                search_state.search_step,
                datetime.now().isoformat(),
                messages_to_delete_str
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния поиска: {e}")
        finally:
            conn.close()

    def get_search_state(self, user_id: int) -> Optional[SearchState]:
        """Получение состояния поиска пользователя (с учетом новых полей)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, origin_code, origin_name, destination_code, destination_name,
                       departure_date, adult_passengers, children_passengers, min_seats,
                       train_numbers, car_types, progress_message_id, selected_train_number, selected_train_info, search_step, messages_to_delete
                FROM search_states 
                WHERE user_id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            if row:
                messages_to_delete = [int(mid) for mid in (row[15] or '').split(',') if mid.strip().isdigit()]
                return SearchState(
                    user_id=row[0],
                    origin_code=row[1],
                    origin_name=row[2],
                    destination_code=row[3],
                    destination_name=row[4],
                    departure_date=row[5],
                    adult_passengers=row[6],
                    children_passengers=row[7],
                    min_seats=row[8],
                    train_numbers=row[9],
                    car_types=row[10],
                    progress_message_id=row[11],
                    selected_train_number=row[12],
                    selected_train_info=row[13],
                    search_step=row[14] if row[14] else 'origin',
                    messages_to_delete=messages_to_delete
                )
            return None
        except Exception as e:
            logger.error(f"Ошибка получения состояния поиска: {e}")
            return None
        finally:
            conn.close()
    
    def clear_search_state(self, user_id: int):
        """Очистка состояния поиска пользователя"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM search_states WHERE user_id = ?', (user_id,))
            conn.commit()
            
        except Exception as e:
            logger.error(f"Ошибка очистки состояния поиска: {e}")
        finally:
            conn.close()


