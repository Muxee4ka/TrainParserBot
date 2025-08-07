"""
Базовый класс для хендлеров
"""
from abc import ABC, abstractmethod
from typing import Any

from aiogram import Router
from aiogram.types import Message, CallbackQuery


class BaseHandler(ABC):
    """Базовый класс для хендлеров"""
    
    def __init__(self, router: Router):
        self.router = router
        self.register_handlers()
    
    @abstractmethod
    def register_handlers(self):
        """Регистрация хендлеров"""
        pass
    
    @abstractmethod
    async def handle(self, event: Any) -> None:
        """Обработка события"""
        pass



