"""
Сервис мониторинга подписок
"""
import asyncio
import logging
import time
from typing import List
from datetime import datetime

from database import DatabaseManager, Subscription
from services.rzd_api import RZDAPIService
from services.notification import NotificationService
from config import config

logger = logging.getLogger(__name__)


class MonitoringService:
    """Сервис мониторинга подписок"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.rzd_api = RZDAPIService()
        self.notification_service = NotificationService()
        self.is_running = False
    
    async def start_monitoring(self):
        """Запуск мониторинга"""
        self.is_running = True
        logger.info("Мониторинг подписок запущен")
        
        while self.is_running:
            try:
                await self.check_all_subscriptions()
                await asyncio.sleep(config.MONITORING_INTERVAL)
            except Exception as e:
                logger.error(f"Ошибка в мониторинге: {e}")
                await asyncio.sleep(60)  # Пауза при ошибке
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.is_running = False
        logger.info("Мониторинг подписок остановлен")
    
    async def check_all_subscriptions(self):
        """Проверка всех активных подписок"""
        try:
            subscriptions = self.db_manager.get_active_subscriptions()
            logger.info(f"Проверяем {len(subscriptions)} активных подписок")
            
            for subscription in subscriptions:
                try:
                    await self.check_single_subscription(subscription)
                except Exception as e:
                    logger.error(f"Ошибка при проверке подписки {subscription.id}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка при проверке подписок: {e}")
    
    def _is_expired(self, subscription: Subscription) -> bool:
        """Дата отправления уже прошла?"""
        try:
            return datetime.fromisoformat(subscription.departure_date).date() < datetime.now().date()
        except (ValueError, TypeError):
            return False

    async def check_single_subscription(self, subscription: Subscription):
        """Проверка одной подписки"""
        try:
            # Подписки на прошедшие даты больше не имеет смысла проверять — деактивируем
            if self._is_expired(subscription):
                self.db_manager.disable_subscription(subscription.id, subscription.user_id)
                logger.info(f"Подписка #{subscription.id} деактивирована: дата отправления прошла")
                return

            # Получаем данные о поездах (блокирующий requests — уводим в отдельный поток)
            trains_data = await asyncio.to_thread(
                self.rzd_api.search_trains,
                origin_code=subscription.origin_code,
                destination_code=subscription.destination_code,
                departure_date=subscription.departure_date,
                adult_passengers=subscription.adult_passengers,
                children_passengers=subscription.children_passengers
            )
            
            # Проверяем наличие мест и готовим краткое состояние (номер поезда -> суммарные места)
            available_trains = []
            state_parts = []
            for train in trains_data['trains']:
                train_number = train.get('TrainNumber', 'N/A')
                # Проверяем фильтр по номерам поездов: в состояние включаем только релевантные
                if subscription.train_numbers:
                    if train_number not in subscription.train_numbers.split(','):
                        continue

                total_seats = self.rzd_api.count_available_seats(train)
                if total_seats >= max(1, subscription.min_seats):
                    available_trains.append(train)
                # Добавляем краткое резюме по релевантному поезду
                state_parts.append(f"{train_number}:{total_seats}")

            current_state = ",".join(sorted(state_parts))
            last_state = self.db_manager.get_subscription_last_state(subscription.id)

            # Отправляем уведомление только если текущая сводка отличается от предыдущей,
            # и одновременно сейчас есть доступные места по условиям подписки.
            if available_trains and current_state != (last_state or ""):
                await self.send_availability_notification(subscription, available_trains)

            # Сохраняем текущее состояние всегда
            self.db_manager.save_subscription_last_state(subscription.id, current_state)
                
        except Exception as e:
            logger.error(f"Ошибка при проверке подписки {subscription.id}: {e}")
    
    async def send_availability_notification(self, subscription: Subscription, trains: List[dict]):
        """Отправка уведомления о появлении мест"""
        try:
            message = self.format_availability_message(subscription, trains)
            purchase_url = self.rzd_api.build_purchase_url(
                subscription.origin_code,
                subscription.destination_code,
                subscription.departure_date
            )
            keyboard = [[{"text": "🎫 Купить на РЖД", "url": purchase_url}]]
            await self.notification_service.send_message(
                subscription.user_id, message, keyboard=keyboard
            )
            logger.info(f"Уведомление отправлено пользователю {subscription.user_id}")

        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
    
    def format_availability_message(self, subscription: Subscription, trains: List[dict]) -> str:
        """Форматирование сообщения о появлении мест"""
        message = f"🔔 Уведомление о появлении мест!\n\n"
        message += f"Подписка #{subscription.id}\n"
        message += f"Маршрут: {subscription.origin_name} -> {subscription.destination_name}\n"
        message += f"Дата: {subscription.departure_date[:10]}\n\n"
        
        for i, train in enumerate(trains[:5], 1):  # Показываем первые 5 поездов
            t = self.rzd_api.extract_train_info(train)
            duration = f" ({t['duration']})" if t['duration'] else ''

            message += f"{i}. 🚂 {t['number']} {t['name']}\n"
            message += f"   ⏰ {t['departure']} → {t['arrival']}{duration}\n"

            # Считаем доступные места с разбивкой по нижним/верхним
            seats = self.rzd_api.count_seats_breakdown(train)
            seats_line = f"   ✅ Доступно мест: {seats['total']}"
            if seats['lower'] or seats['upper']:
                seats_line += f" (низ {seats['lower']} / верх {seats['upper']})"
            message += seats_line + "\n"

            price = self.rzd_api.min_price(train)
            if price:
                message += f"   💰 от {price:.0f} ₽\n"
            message += "\n"

        return message
