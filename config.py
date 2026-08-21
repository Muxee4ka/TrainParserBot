"""
Конфигурация бота
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Бандл сертификатов НУЦ Минцифры, лежит рядом с этим файлом.
_DEFAULT_CA_BUNDLE = Path(__file__).resolve().parent / "certs" / "russian_trusted.pem"

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
    # CA-бандл для запросов к РЖД: сайт живёт на сертификате НУЦ Минцифры,
    # которого нет ни в certifi, ни в системном store, плюс сервер не отдаёт
    # промежуточный Sub CA. Подробнее — certs/README.md.
    RZD_CA_BUNDLE: str = os.getenv("RZD_CA_BUNDLE", str(_DEFAULT_CA_BUNDLE))
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


def rzd_verify():
    """Значение для параметра `verify=` в запросах к РЖД.

    Возвращает путь к бандлу Минцифры; если файла нет или RZD_CA_BUNDLE пуст —
    True, то есть обычная проверка по certifi.
    """
    bundle = config.RZD_CA_BUNDLE
    if bundle and os.path.isfile(bundle):
        return bundle
    return True

def ensure_data_directory():
    """Создает директорию для данных если её нет"""
    os.makedirs("data", exist_ok=True)



