"""
Конфигурация бота
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    """Конфигурация бота"""
    # Telegram Bot Token
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    # API URLs
    RZD_API_URL: str = os.getenv("RZD_API_URL", "https://ticket.rzd.ru/api/v1/railway-service/prices/train-pricing")
    RZD_SUGGEST_URL: str = os.getenv("RZD_SUGGEST_URL", "https://ticket.rzd.ru/api/v1/suggests")
    # User Agent
    USER_AGENT: str = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/train_subscriptions.db")
    # Monitoring settings
    MONITORING_INTERVAL: int = int(os.getenv("MONITORING_INTERVAL", 300))
    # Message limits
    MAX_MESSAGE_LENGTH: int = int(os.getenv("MAX_MESSAGE_LENGTH", 4000))
    MAX_CALLBACK_DATA_LENGTH: int = int(os.getenv("MAX_CALLBACK_DATA_LENGTH", 64))
    # Station search settings
    MAX_STATIONS_PER_SEARCH: int = int(os.getenv("MAX_STATIONS_PER_SEARCH", 10))
    MIN_QUERY_LENGTH: int = int(os.getenv("MIN_QUERY_LENGTH", 2))
    # Train search settings
    MAX_TRAINS_PER_RESULT: int = int(os.getenv("MAX_TRAINS_PER_RESULT", 10))

# Создаем экземпляр конфигурации
config = Config()

def ensure_data_directory():
    """Создает директорию для данных если её нет"""
    os.makedirs("data", exist_ok=True)



