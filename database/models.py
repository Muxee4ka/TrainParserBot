"""
Модели базы данных
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class Subscription:
    """Модель подписки"""
    id: Optional[int]
    user_id: int
    origin_code: str
    origin_name: str
    destination_code: str
    destination_name: str
    departure_date: str
    train_numbers: str
    car_types: str
    min_seats: int
    adult_passengers: int
    children_passengers: int
    interval_minutes: int
    is_active: bool
    created_at: datetime


@dataclass
class SearchState:
    """Модель состояния поиска пользователя"""
    user_id: int
    origin_code: Optional[str] = None
    origin_name: Optional[str] = None
    destination_code: Optional[str] = None
    destination_name: Optional[str] = None
    departure_date: Optional[str] = None
    adult_passengers: int = 1
    children_passengers: int = 0
    min_seats: int = 1
    train_numbers: str = ""
    car_types: str = ""
    progress_message_id: Optional[int] = None  # ID сообщения с прогрессом
    selected_train_number: Optional[str] = None  # выбранный поезд
    selected_train_info: Optional[str] = None  # краткая инфа о поезде
    search_step: str = 'origin'  # этап поиска: origin, destination, date, train, done
    messages_to_delete: List[int] = field(default_factory=list)  # id сообщений для удаления


