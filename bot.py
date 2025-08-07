"""
Главный файл бота
"""
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import config, ensure_data_directory
from handlers import CommandsHandler, SearchHandler
from services.monitoring import MonitoringService

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class TrainBot:
    """Главный класс бота"""

    def __init__(self):
        self.bot = Bot(
            token=config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        self.monitoring_service = MonitoringService()

        # Регистрируем хендлеры
        self._register_handlers()

    def _register_handlers(self):
        """Регистрация хендлеров"""
        # Создаем роутеры
        commands_router = Router()
        search_router = Router()

        # Регистрируем хендлеры
        CommandsHandler(commands_router)
        SearchHandler(search_router)

        # Включаем роутеры в диспетчер
        self.dp.include_router(commands_router)
        self.dp.include_router(search_router)

    async def start(self):
        """Запуск бота"""
        try:
            logger.info("Запуск бота...")

            # Запускаем мониторинг в отдельной задаче
            monitoring_task = asyncio.create_task(
                self.monitoring_service.start_monitoring()
            )

            # Запускаем бота
            await self.dp.start_polling(self.bot)

        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            raise
        finally:
            # Останавливаем мониторинг
            self.monitoring_service.stop_monitoring()
            if 'monitoring_task' in locals():
                monitoring_task.cancel()

    async def stop(self):
        """Остановка бота"""
        try:
            logger.info("Остановка бота...")
            await self.bot.session.close()
        except Exception as e:
            logger.error(f"Ошибка остановки бота: {e}")


async def main():
    """Главная функция"""
    try:
        # Создаем директорию для данных
        ensure_data_directory()

        # Создаем и запускаем бота
        bot = TrainBot()
        await bot.start()

    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
