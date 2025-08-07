"""
Хендлеры для команд
"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from handlers.base import BaseHandler
from services.notification import NotificationService
from database import DatabaseManager

logger = logging.getLogger(__name__)


class CommandsHandler(BaseHandler):
    """Хендлер для команд"""
    
    def __init__(self, router: Router):
        self.notification_service = NotificationService()
        self.db_manager = DatabaseManager()
        super().__init__(router)
    
    def register_handlers(self):
        """Регистрация хендлеров"""
        self.router.message.register(self.start_command, Command("start"))
        self.router.message.register(self.help_command, Command("help"))
        self.router.message.register(self.subscriptions_command, Command("subscriptions"))
    
    async def start_command(self, message: Message):
        """Обработчик команды /start"""
        welcome_text = """
🚆 Добро пожаловать в бот поиска поездов РЖД!

Доступные команды:
/search - Начать поиск поездов
/subscribe - Подписаться на отслеживание
/subscriptions - Мои подписки
/help - Помощь

💡 Для поиска просто напишите название станции отправления!
        """
        await message.answer(welcome_text.strip())
    
    async def help_command(self, message: Message):
        """Обработчик команды /help"""
        help_text = """
📖 Справка по использованию бота:

🔍 Поиск поездов:
   • Просто напишите название станции отправления
   • Выберите станцию из списка
   • Введите станцию назначения
   • Укажите дату поездки (ДД.ММ.ГГГГ)

🔔 Подписка на отслеживание:
   • После поиска выберите "Подписаться на отслеживание"
   • Бот будет проверять наличие мест каждые 5 минут
   • Уведомления придут автоматически

📋 Управление подписками:
   • /subscriptions - просмотр всех подписок
   • Нажмите "Отключить" для отключения подписки

💡 Советы:
• Используйте точные названия станций (Москва, Санкт-Петербург)
• Дата в формате: 15.01.2025
• Минимальный интервал проверки: 5 минут
        """
        await message.answer(help_text.strip())
    
    async def subscriptions_command(self, message: Message):
        """Обработчик команды /subscriptions"""
        try:
            user_id = message.from_user.id
            subscriptions = self.db_manager.get_user_subscriptions(user_id)
            
            if not subscriptions:
                await message.answer("У вас пока нет подписок. Используйте поиск для создания подписки.")
                return
            
            message_text = "📋 Ваши подписки:\n\n"
            keyboard = []
            
            for subscription in subscriptions:
                status = "✅ Активна" if subscription.is_active else "❌ Отключена"
                message_text += f"🔔 Подписка #{subscription.id}\n"
                message_text += f"   Маршрут: {subscription.origin_name} -> {subscription.destination_name}\n"
                message_text += f"   Дата: {subscription.departure_date[:10]}\n"
                message_text += f"   Статус: {status}\n\n"
                
                if subscription.is_active:
                    keyboard.append([{
                        "text": f"❌ Отключить #{subscription.id}",
                        "callback_data": f"disable_sub_{subscription.id}"
                    }])
            
            if keyboard:
                await self.notification_service.send_message_with_keyboard(
                    user_id, message_text, keyboard
                )
            else:
                await message.answer(message_text)
                
        except Exception as e:
            logger.error(f"Ошибка при получении подписок: {e}")
            await message.answer("❌ Ошибка при получении подписок")
    
    async def handle(self, event: Message) -> None:
        """Обработка события"""
        pass
