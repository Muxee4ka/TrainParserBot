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
from services.filters import format_filter_summary, matched_unit
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

    @staticmethod
    def count_matched(rzd_api, subscription, train) -> int:
        """Сколько мест поезда подходит под фильтр подписки.

        Для berth 'cabin'/'pair'/'together' считает через схему вагонов (CarPricing) —
        агрегатных данных недостаточно. Иначе — match_seats.
        """
        from services.rzd_seatmap import SeatMapService, SEATMAP_BERTHS
        if subscription.berth in SEATMAP_BERTHS:
            car_types = [c for c in (subscription.car_types or '').split(',') if c]
            n = SeatMapService().count_for_berth(
                subscription.berth,
                subscription.origin_code, subscription.destination_code,
                train.get('LocalDepartureDateTime'),
                train.get('TrainNumber') or train.get('DisplayTrainNumber') or '',
                train.get('Provider', 'P1'),
                car_types=car_types or None, max_price=subscription.max_price,
                min_count=subscription.min_seats,
            )
            return n or 0
        car_types = [c for c in (subscription.car_types or '').split(',') if c]
        return rzd_api.match_seats(
            train, car_types=car_types or None,
            berth=subscription.berth, max_price=subscription.max_price,
        )['total']

    @classmethod
    def _filtered_state(cls, rzd_api, subscription, trains: list):
        """Возвращает (подходящие_поезда, строка_состояния) с учётом фильтров подписки."""
        available, parts = [], []
        for train in trains:
            number = rzd_api.extract_train_info(train)['number']
            if subscription.train_numbers and number not in subscription.train_numbers.split(','):
                continue
            count = cls.count_matched(rzd_api, subscription, train)
            if count >= max(1, subscription.min_seats):
                available.append(train)
            parts.append(f"{number}:{count}")
        return available, ",".join(sorted(parts))

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
            
            # Проверяем наличие мест (с учётом фильтров подписки) и готовим краткое состояние.
            # Для фильтра «купе целиком» внутри идёт сетевой запрос схемы вагонов — уводим в поток.
            available_trains, current_state = await asyncio.to_thread(
                self._filtered_state, self.rzd_api, subscription, trains_data['trains']
            )
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
            # для cabin внутри идёт сетевой запрос схемы вагонов — уводим в поток
            message = await asyncio.to_thread(self.format_availability_message, subscription, trains)
            # резолв nodeId делает сетевые запросы — уводим в поток
            purchase_url = await asyncio.to_thread(
                self.rzd_api.build_purchase_url,
                subscription.origin_code, subscription.destination_code,
                subscription.departure_date,
                subscription.origin_name, subscription.destination_name,
                subscription.adult_passengers,
            )
            keyboard = [[{"text": "🎫 Купить на РЖД", "url": purchase_url, "style": "success"}]]
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

        car_types = [c for c in (subscription.car_types or '').split(',') if c]
        berth = subscription.berth
        max_price = subscription.max_price

        summary = format_filter_summary(subscription.car_types, berth, max_price, subscription.min_seats)
        message += f"Фильтр: {summary}\n\n"

        for i, train in enumerate(trains[:5], 1):  # Показываем первые 5 поездов
            t = self.rzd_api.extract_train_info(train)
            duration = f" ({t['duration']})" if t['duration'] else ''

            message += f"{i}. 🚂 {t['number']} {t['name']}\n"
            message += f"   ⏰ {t['departure']} → {t['arrival']}{duration}\n"

            unit = matched_unit(berth)
            from services.rzd_seatmap import SeatMapService, SEATMAP_BERTHS, format_seatmap_detail
            if berth in SEATMAP_BERTHS:
                # точный список купе через схему вагонов (с номерами)
                detail = SeatMapService().detail_for_berth(
                    berth,
                    subscription.origin_code, subscription.destination_code,
                    train.get('LocalDepartureDateTime'),
                    train.get('TrainNumber') or train.get('DisplayTrainNumber') or '',
                    train.get('Provider', 'P1'),
                    car_types=car_types or None, max_price=max_price,
                    min_count=subscription.min_seats,
                ) or []
                message += f"   ✅ Доступно ({unit}): {len(detail)}\n"
                if detail:
                    message += f"   🚪 {format_seatmap_detail(berth, detail)}\n"
            else:
                m = self.rzd_api.match_seats(
                    train, car_types=car_types or None, berth=berth, max_price=max_price
                )
                seats_line = f"   ✅ Доступно ({unit}): {m['total']}"
                if m['lower'] or m['upper']:
                    seats_line += f" (низ {m['lower']} / верх {m['upper']})"
                message += seats_line + "\n"
                if m['min_price']:
                    message += f"   💰 от {m['min_price']:.0f} ₽\n"
            message += "\n"

        return message
