"""
Хендлеры для поиска
"""
import asyncio
import json
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from handlers.base import BaseHandler
from services.rzd_api import RZDAPIService
from services.notification import NotificationService
from services.monitoring import MonitoringService
from services import filters as flt
from database import DatabaseManager, SearchState, Subscription
from config import config

logger = logging.getLogger(__name__)


class SearchHandler(BaseHandler):
    """Хендлер для поиска"""
    
    def __init__(self, router: Router):
        self.rzd_api = RZDAPIService()
        self.notification_service = NotificationService()
        self.db_manager = DatabaseManager()
        super().__init__(router)
    
    def register_handlers(self):
        """Регистрация хендлеров"""
        # Обработка команды /search
        self.router.message.register(self.search_command, Command("search"))
        
        # Обработка текстовых сообщений (поиск станций)
        self.router.message.register(self.handle_text_message, F.text)
        
        # Обработка callback запросов
        self.router.callback_query.register(self.handle_callback)

    def format_progress_message(self, search_state: SearchState) -> str:
        """Формирует текст прогресс-сообщения для поиска поездов"""
        origin = search_state.origin_name or 'не выбрана'
        destination = search_state.destination_name or 'не выбрана'
        date = (
            datetime.strptime(search_state.departure_date, '%Y-%m-%dT%H:%M:%S').strftime('%d.%m.%Y')
            if search_state.departure_date else 'не выбрана'
        )
        msg = (
            '🚆 <b>Поиск поездов</b>\n\n'
            f'Станция отправления: <b>{origin}</b>\n'
            f'Станция назначения: <b>{destination}</b>\n'
            f'Дата: <b>{date}</b>\n'
        )
        return msg

    _WEEKDAYS_RU = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

    def _date_keyboard(self, days: int = 14) -> list:
        """Кнопки выбора даты на ближайшие N дней (по 2 в ряд)."""
        from datetime import date, timedelta
        today = date.today()
        rows, row = [], []
        for i in range(days):
            d = today + timedelta(days=i)
            if i == 0:
                label = f"Сегодня {d.strftime('%d.%m')}"
            elif i == 1:
                label = f"Завтра {d.strftime('%d.%m')}"
            else:
                label = f"{d.strftime('%d.%m')} ({self._WEEKDAYS_RU[d.weekday()]})"
            row.append({"text": label, "callback_data": f"pickdate_{d.strftime('%Y-%m-%d')}"})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        return rows

    def _build_train_list(self, trains_data: dict):
        """Строит (текст, клавиатуру) списка поездов для выбора."""
        trains = trains_data.get('trains', [])
        text = f"Найдено поездов: {trains_data.get('total_count', len(trains))}\nВыберите поезд для отслеживания:"
        keyboard = []
        for i, train in enumerate(trains, 1):
            t = self.rzd_api.extract_train_info(train)
            number = t['number']
            duration = f" ({t['duration']})" if t['duration'] else ''
            price = self.rzd_api.min_price(train)
            price_str = f" · от {price:.0f} ₽" if price else ''
            brand = " 🔹ФИРМ" if train.get('IsBranded') else ''
            text += f"\n{i}. 🚂 <b>{number}</b>{brand} {t['name']} {t['departure']}→{t['arrival']}{duration}{price_str}"
            btn_parts = [f"🚆 {number}"]
            if train.get('IsBranded'):
                btn_parts.append("ФИРМ")
            if t['name']:
                btn_parts.append(t['name'])
            if price:
                btn_parts.append(f"от {price:.0f} ₽")
            keyboard.append([{
                "text": " · ".join(btn_parts),
                "callback_data": f"select_train_{number}_{t['name'][:20].replace(' ', '')}"
            }])
        return text, keyboard

    async def _load_and_show_trains(self, chat_id: int, search_state: SearchState):
        """Ищет поезда по выбранным параметрам и показывает список (общий путь)."""
        trains_data = await asyncio.to_thread(
            self.rzd_api.search_trains,
            origin_code=search_state.origin_code,
            destination_code=search_state.destination_code,
            departure_date=search_state.departure_date,
            adult_passengers=search_state.adult_passengers,
            children_passengers=search_state.children_passengers,
        )
        if not trains_data.get('trains'):
            progress_text = self.format_progress_message(search_state) + '\n❌ Поезда не найдены на выбранную дату.'
            await self._edit_progress(chat_id, search_state, progress_text, keyboard=self._date_keyboard())
            return
        text, keyboard = self._build_train_list(trains_data)
        progress_text = self.format_progress_message(search_state) + '\n' + text
        if len(progress_text) > config.MAX_MESSAGE_LENGTH:
            progress_text = progress_text[:config.MAX_MESSAGE_LENGTH] + "\n\n... (сообщение обрезано)"
        await self._edit_progress(chat_id, search_state, progress_text, keyboard=keyboard)

    async def _edit_progress(self, chat_id: int, search_state: SearchState, text: str, keyboard=None):
        """Редактирует прогресс-сообщение на месте либо отправляет новое (с сохранением id)."""
        if search_state.progress_message_id:
            await self.notification_service.edit_message(
                chat_id, search_state.progress_message_id, text, keyboard=keyboard, parse_mode='HTML'
            )
        else:
            sent_id = await self.notification_service.send_message_with_keyboard(chat_id, text, keyboard or [])
            if sent_id:
                search_state.progress_message_id = sent_id
        self.db_manager.save_search_state(search_state)

    def _panel_text(self, breakdown: dict, matched: dict, filter_summary: str,
                    matched_unit: str = "мест") -> str:
        by_type = " · ".join(f"{k} {v}" for k, v in breakdown.get("by_type", {}).items()) or "—"
        price = breakdown.get("min_price")
        price_str = f" · от {price:.0f} ₽" if price else ""
        berths = f"низ {breakdown.get('lower', 0)} / верх {breakdown.get('upper', 0)} / бок {breakdown.get('side', 0)}"
        return (
            f"🚆 <b>Наличие мест</b>\n"
            f"Найдено мест: {breakdown.get('total', 0)}\n"
            f"{by_type}  |  {berths}{price_str}\n\n"
            f"Фильтр: <b>{filter_summary}</b>\n"
            f"Под фильтр подходит: {matched.get('total', 0)} {matched_unit}\n\n"
            f"Настройте фильтр кнопками ниже и нажмите «Подписаться»."
        )

    async def search_command(self, message: Message):
        """Обработчик команды /search"""
        user_id = message.from_user.id
        search_state = self.db_manager.get_search_state(user_id) or SearchState(user_id=user_id)
        # Сбросить старое состояние поиска
        search_state.origin_code = None
        search_state.origin_name = None
        search_state.destination_code = None
        search_state.destination_name = None
        search_state.departure_date = None
        search_state.progress_message_id = None
        search_state.selected_train_number = None
        search_state.selected_train_info = None
        search_state.search_step = 'origin'
        self.db_manager.save_search_state(search_state)
        progress_text = self.format_progress_message(search_state) + '\nВведите название станции отправления:'
        sent = await message.answer(progress_text, parse_mode='HTML')
        search_state.progress_message_id = sent.message_id
        self.db_manager.save_search_state(search_state)

    async def handle_text_message(self, message: Message):
        """Обработка текстовых сообщений с учетом этапа поиска"""
        try:
            user_id = message.from_user.id
            text = message.text.strip()
            search_state = self.db_manager.get_search_state(user_id)
            logger.info(f"[handle_text_message] user_id={user_id} search_step={getattr(search_state, 'search_step', None)} text='{text}'")
            if not search_state:
                search_state = SearchState(user_id=user_id)
            # Если это не progress_message, добавить в messages_to_delete
            if message.message_id != search_state.progress_message_id:
                search_state.messages_to_delete.append(message.message_id)
                self.db_manager.save_search_state(search_state)
            # Явная логика по этапу поиска
            if search_state.search_step == 'origin':
                await self.search_stations(message, text, search_state, step='origin')
            elif search_state.search_step == 'destination':
                await self.search_stations(message, text, search_state, step='destination')
            elif search_state.search_step == 'date':
                await self.handle_date_input(message, search_state)
            else:
                sent = await message.answer('Используйте кнопки для выбора поезда или подписки.')
                search_state.messages_to_delete.append(sent.message_id)
                self.db_manager.save_search_state(search_state)
        except Exception as e:
            logger.error(f"Ошибка обработки текстового сообщения: {e}")
            sent = await message.answer("❌ Произошла ошибка. Попробуйте позже.")
            search_state = self.db_manager.get_search_state(message.from_user.id) or SearchState(user_id=message.from_user.id)
            search_state.messages_to_delete.append(sent.message_id)
            self.db_manager.save_search_state(search_state)

    async def search_stations(self, message: Message, query: str, search_state: SearchState, step: str):
        """Поиск станций для отправления или назначения"""
        if len(query) < config.MIN_QUERY_LENGTH:
            sent = await message.answer(f"Введите минимум {config.MIN_QUERY_LENGTH} символа для поиска станции")
            search_state.messages_to_delete.append(sent.message_id)
            self.db_manager.save_search_state(search_state)
            return
        try:
            stations = await asyncio.to_thread(self.rzd_api.search_stations, query)
            if not stations:
                sent = await message.answer("Станции не найдены. Попробуйте другой запрос.")
                search_state.messages_to_delete.append(sent.message_id)
                self.db_manager.save_search_state(search_state)
                return
            keyboard = []
            options = {}  # код -> имя, чтобы надёжно восстановить имя (callback не вмещает длинные)
            for station in stations:
                station_name = self.rzd_api.format_station_name(station)
                callback_data = self.rzd_api.create_safe_callback_data(station)
                code = str(station.get('expressCode', ''))
                if code:
                    options[code] = station_name
                keyboard.append([{
                    "text": f"🚉 {station_name}",
                    "callback_data": callback_data
                }])
            # запоминаем карту код->имя (объединяем с прошлой, чтобы хватило на оба шага)
            try:
                prev = json.loads(search_state.station_options or '{}')
            except Exception:
                prev = {}
            prev.update(options)
            search_state.station_options = json.dumps(prev, ensure_ascii=False)
            self.db_manager.save_search_state(search_state)
            prompt = 'Выберите станцию отправления:' if step == 'origin' else 'Выберите станцию назначения:'
            sent_id = await self.notification_service.send_message_with_keyboard(
                message.from_user.id,
                f"Найденные станции для запроса '{query}':\n{prompt}",
                keyboard
            )
            # Клавиатуру со списком станций надо удалить после выбора — кладём её id в messages_to_delete
            if sent_id:
                search_state.messages_to_delete.append(sent_id)
                self.db_manager.save_search_state(search_state)
        except Exception as e:
            logger.error(f"Ошибка поиска станций: {e}")
            sent = await message.answer("Ошибка при поиске станций. Попробуйте позже.")
            search_state.messages_to_delete.append(sent.message_id)
            self.db_manager.save_search_state(search_state)

    async def handle_callback(self, callback: CallbackQuery):
        """Обработка callback запросов (добавить select_train_)"""
        try:
            data = callback.data
            if data.startswith("station_"):
                await self.handle_station_selection(callback)
            elif data.startswith("pickdate_"):
                await self.handle_date_pick(callback)
            elif data == "search_trains":
                await self.search_trains(callback)
            elif data == "subscribe_search":
                await self.subscribe_to_search(callback)
            elif data.startswith("select_train_"):
                await self.handle_select_train(callback)
            elif data == "subscribe_selected_train":
                await self.subscribe_to_selected_train(callback)
            elif data.startswith("subscribe_train_"):
                await self.subscribe_to_train(callback)
            elif data.startswith("disable_sub_"):
                await self.disable_subscription(callback)
            elif data.startswith("enable_sub_"):
                await self.enable_subscription(callback)
            elif data.startswith("check_sub_"):
                await self.check_subscription_now(callback)
            elif data.startswith("delsub_"):
                await self.confirm_delete_subscription(callback)
            elif data.startswith("dodelsub_"):
                await self.delete_subscription(callback)
            elif data == "canceldel":
                await self.cancel_delete_subscription(callback)
            elif data.startswith("flt_"):
                await self.handle_filter_toggle(callback)
            elif data == "subscribe_filtered":
                await self.subscribe_to_selected_train(callback)
            elif data.startswith("editflt_"):
                await self.handle_edit_filters(callback)
            elif data == "save_filters":
                await self.save_subscription_filters(callback)
            else:
                await callback.answer("Неизвестная команда")
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}")
            await callback.answer("❌ Произошла ошибка")

    async def _delete_user_messages(self, chat_id: int, search_state: SearchState):
        """Удаляет все сообщения из search_state.messages_to_delete, очищает список."""
        for msg_id in getattr(search_state, 'messages_to_delete', []):
            if msg_id and msg_id != search_state.progress_message_id:
                await self.notification_service.delete_message(chat_id, msg_id)
        search_state.messages_to_delete = []
        self.db_manager.save_search_state(search_state)

    async def handle_station_selection(self, callback: CallbackQuery):
        """Обработка выбора станции (рефакторинг: редактируем прогресс-сообщение)"""
        try:
            data = callback.data
            user_id = callback.from_user.id
            parts = data.split('_', 2)
            if len(parts) < 2:
                await callback.answer('❌ Ошибка при обработке выбора станции')
                return
            station_code = parts[1]
            search_state = self.db_manager.get_search_state(user_id)
            if not search_state:
                search_state = SearchState(user_id=user_id)
            # Имя станции: 1) из карты код->имя (надёжно, callback не вмещает длинные),
            # 2) из callback, 3) фолбэк — код.
            try:
                options = json.loads(search_state.station_options or '{}')
            except Exception:
                options = {}
            station_name = options.get(station_code)
            if not station_name and len(parts) > 2 and parts[2].strip():
                station_name = parts[2]
            if not station_name:
                station_name = station_code
            # Если сообщение с кнопками не совпадает с progress_message, добавить в messages_to_delete
            if callback.message.message_id != search_state.progress_message_id:
                search_state.messages_to_delete.append(callback.message.message_id)
                self.db_manager.save_search_state(search_state)
            logger.info(f"[handle_station_selection] user_id={user_id} search_step(before)={search_state.search_step} station_code={station_code} station_name={station_name}")
            # Определяем, какую станцию выбираем
            if search_state.search_step == 'origin':
                search_state.origin_code = station_code
                search_state.origin_name = station_name
                search_state.search_step = 'destination'
                next_step = '\nТеперь введите название станции назначения:'
                logger.info(f"[handle_station_selection] user_id={user_id} set search_step=destination")
            elif search_state.search_step == 'destination':
                search_state.destination_code = station_code
                search_state.destination_name = station_name
                search_state.search_step = 'date'
                next_step = '\nВыберите дату поездки кнопкой ниже (или введите вручную ДД.ММ.ГГГГ):'
                logger.info(f"[handle_station_selection] user_id={user_id} set search_step=date")
            else:
                await callback.answer('❌ Неожиданный этап выбора станции')
                return
            self.db_manager.save_search_state(search_state)
            logger.info(f"[handle_station_selection] user_id={user_id} search_step(after)={search_state.search_step}")
            progress_text = self.format_progress_message(search_state) + next_step
            # на шаге даты показываем календарь-кнопки
            step_keyboard = self._date_keyboard() if search_state.search_step == 'date' else None
            if search_state.progress_message_id:
                await self.notification_service.edit_message(
                    callback.message.chat.id,
                    search_state.progress_message_id,
                    progress_text,
                    keyboard=step_keyboard,
                    parse_mode='HTML'
                )
            else:
                sent_id = await self.notification_service.send_message_with_keyboard(
                    callback.message.chat.id, progress_text, step_keyboard or []
                )
                if sent_id:
                    search_state.progress_message_id = sent_id
                self.db_manager.save_search_state(search_state)
            # Удаляем все сообщения пользователя кроме progress_message_id
            await self._delete_user_messages(callback.message.chat.id, search_state)
            await callback.answer()
        except Exception as e:
            logger.error(f'Ошибка обработки выбора станции: {e}')
            await callback.answer('❌ Ошибка при обработке выбора станции')
    
    async def _apply_date_and_show_trains(self, chat_id: int, search_state: SearchState, date_obj):
        """Общий путь после выбора даты (кнопкой или вводом): валидация + список поездов."""
        if date_obj.date() < datetime.now().date():
            progress_text = self.format_progress_message(search_state) + '\n❌ Дата не может быть в прошлом. Выберите будущую дату.'
            await self._edit_progress(chat_id, search_state, progress_text, keyboard=self._date_keyboard())
            await self._delete_user_messages(chat_id, search_state)
            return
        search_state.departure_date = date_obj.strftime("%Y-%m-%dT00:00:00")
        search_state.search_step = 'train'
        self.db_manager.save_search_state(search_state)
        await self._load_and_show_trains(chat_id, search_state)
        await self._delete_user_messages(chat_id, search_state)

    async def handle_date_pick(self, callback: CallbackQuery):
        """Выбор даты кнопкой-календарём (callback pickdate_YYYY-MM-DD)."""
        try:
            user_id = callback.from_user.id
            search_state = self.db_manager.get_search_state(user_id)
            if not search_state:
                await callback.answer('❌ Ошибка состояния поиска')
                return
            date_obj = datetime.strptime(callback.data.split('_', 1)[1], "%Y-%m-%d")
            await callback.answer("Ищу поезда…")
            await self._apply_date_and_show_trains(callback.message.chat.id, search_state, date_obj)
        except Exception as e:
            logger.error(f"Ошибка выбора даты кнопкой: {e}")
            await callback.answer('❌ Ошибка при выборе даты')

    async def handle_date_input(self, message: Message, search_state: SearchState):
        """Обработка ручного ввода даты (ДД.ММ.ГГГГ)."""
        try:
            date_obj = datetime.strptime(message.text.strip(), "%d.%m.%Y")
        except ValueError:
            progress_text = self.format_progress_message(search_state) + '\nНеверный формат даты. Используйте кнопки ниже или формат ДД.ММ.ГГГГ (например: 15.01.2026)'
            await self._edit_progress(message.chat.id, search_state, progress_text, keyboard=self._date_keyboard())
            await self._delete_user_messages(message.chat.id, search_state)
            return
        try:
            await self._apply_date_and_show_trains(message.chat.id, search_state, date_obj)
        except Exception as e:
            logger.error(f"Ошибка обработки даты: {e}")
            progress_text = self.format_progress_message(search_state) + '\n❌ Ошибка при обработке даты'
            await self._edit_progress(message.chat.id, search_state, progress_text, keyboard=self._date_keyboard())
            await self._delete_user_messages(message.chat.id, search_state)

    async def search_trains(self, callback: CallbackQuery):
        """Поиск поездов"""
        try:
            user_id = callback.from_user.id
            search_state = self.db_manager.get_search_state(user_id)
            
            if not search_state or not all([
                search_state.origin_code, 
                search_state.destination_code, 
                search_state.departure_date
            ]):
                await callback.message.edit_text("❌ Не все параметры поиска заполнены")
                return
            
            await callback.message.edit_text("🔍 Ищу поезда...")

            # Поиск поездов через API (блокирующий requests — уводим в поток)
            trains_data = await asyncio.to_thread(
                self.rzd_api.search_trains,
                origin_code=search_state.origin_code,
                destination_code=search_state.destination_code,
                departure_date=search_state.departure_date,
                adult_passengers=search_state.adult_passengers,
                children_passengers=search_state.children_passengers
            )
            
            # Форматируем результат
            message = self.format_trains_message(trains_data, search_state)
            
            # Проверяем длину сообщения
            if len(message) > config.MAX_MESSAGE_LENGTH:
                message = message[:config.MAX_MESSAGE_LENGTH] + "\n\n... (сообщение обрезано)"
            
            await callback.message.edit_text(message, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Ошибка поиска поездов: {e}")
            await callback.message.edit_text("❌ Ошибка при поиске поездов. Попробуйте позже.")
    
    def format_trains_message_with_subscription(self, trains_data: dict, search_state: SearchState) -> tuple[str, list]:
        """Форматирование сообщения с результатами поиска и кнопками подписки"""
        trains = trains_data.get('trains', [])
        
        if not trains:
            return (f"❌ Поезда не найдены\n\n"
                   f"Маршрут: {search_state.origin_name} -> {search_state.destination_name}\n"
                   f"Дата: {search_state.departure_date[:10]}"), []
        
        message = f"🚆 Найдено поездов: {trains_data['total_count']}\n\n"
        message += f"Маршрут: {search_state.origin_name} -> {search_state.destination_name}\n"
        message += f"Дата: {search_state.departure_date[:10]}\n\n"
        
        keyboard = []

        for i, train in enumerate(trains, 1):
            t = self.rzd_api.extract_train_info(train)
            train_number = t['number']
            duration = f" ({t['duration']})" if t['duration'] else ''

            message += f"{i}. 🚂 <b>{train_number}</b> {t['name']}\n"
            message += f"   ⏰ {t['departure']} -> {t['arrival']}{duration}\n"

            # Информация о местах
            available_seats = self.rzd_api.count_available_seats(train)
            if available_seats > 0:
                message += f"   ✅ Доступно мест: {available_seats}\n"
                price = self.rzd_api.min_price(train)
                if price:
                    message += f"   💰 от {price:.0f} ₽\n"
            else:
                message += f"   ❌ Нет свободных мест\n"

            message += "\n"

            # Добавляем кнопку для подписки на этот поезд
            keyboard.append([{
                "text": f"🔔 Подписаться на {train_number}",
                "callback_data": f"subscribe_train_{train_number}"
            }])

        return message, keyboard

    def format_trains_message(self, trains_data: dict, search_state: SearchState) -> str:
        """Форматирование сообщения с результатами поиска"""
        trains = trains_data.get('trains', [])
        
        if not trains:
            return (f"❌ Поезда не найдены\n\n"
                   f"Маршрут: {search_state.origin_name} -> {search_state.destination_name}\n"
                   f"Дата: {search_state.departure_date[:10]}")
        
        message = f"🚆 Найдено поездов: {trains_data['total_count']}\n\n"
        message += f"Маршрут: {search_state.origin_name} -> {search_state.destination_name}\n"
        message += f"Дата: {search_state.departure_date[:10]}\n\n"
        
        for i, train in enumerate(trains, 1):
            t = self.rzd_api.extract_train_info(train)
            duration = f" ({t['duration']})" if t['duration'] else ''

            message += f"{i}. 🚂 <b>{t['number']}</b> {t['name']}\n"
            message += f"   ⏰ {t['departure']} -> {t['arrival']}{duration}\n"

            # Информация о местах
            available_seats = self.rzd_api.count_available_seats(train)
            if available_seats > 0:
                message += f"   ✅ Доступно мест: {available_seats}\n"
                price = self.rzd_api.min_price(train)
                if price:
                    message += f"   💰 от {price:.0f} ₽\n"
            else:
                message += f"   ❌ Нет свободных мест\n"

            message += "\n"

        return message
    
    async def subscribe_to_train(self, callback: CallbackQuery):
        """Подписка на конкретный поезд (очищаем progress_message_id после завершения)"""
        try:
            data = callback.data
            user_id = callback.from_user.id
            train_number = data.split("_")[-1]
            search_state = self.db_manager.get_search_state(user_id)
            if not search_state or not all([
                search_state.origin_code, 
                search_state.destination_code, 
                search_state.departure_date
            ]):
                progress_text = self.format_progress_message(search_state) + '\n❌ Не все параметры поиска заполнены'
                if search_state and search_state.progress_message_id:
                    await self.notification_service.edit_message(
                        callback.message.chat.id,
                        search_state.progress_message_id,
                        progress_text,
                        parse_mode='HTML'
                    )
                else:
                    await callback.message.edit_text(progress_text, parse_mode='HTML')
                return
            # Создаем подписку на конкретный поезд
            subscription = Subscription(
                id=None,
                user_id=user_id,
                origin_code=search_state.origin_code,
                origin_name=search_state.origin_name,
                destination_code=search_state.destination_code,
                destination_name=search_state.destination_name,
                departure_date=search_state.departure_date,
                train_numbers=train_number,  # Указываем конкретный поезд
                car_types=search_state.car_types,
                min_seats=search_state.min_seats,
                adult_passengers=search_state.adult_passengers,
                children_passengers=search_state.children_passengers,
                interval_minutes=5,
                is_active=True,
                created_at=datetime.now()
            )
            subscription_id = self.db_manager.create_subscription(subscription)
            if subscription_id:
                result_text = (
                    f"✅ Подписка создана!\n\n"
                    f"Поезд: <b>{train_number}</b>\n"
                    f"Маршрут: {search_state.origin_name} -> {search_state.destination_name}\n"
                    f"Дата: {search_state.departure_date[:10]}\n\n"
                    f"Бот будет проверять наличие мест в поезде {train_number} каждые 5 минут и уведомит вас при их появлении."
                )
                if search_state.progress_message_id:
                    await self.notification_service.edit_message(
                        callback.message.chat.id,
                        search_state.progress_message_id,
                        result_text,
                        parse_mode='HTML'
                    )
                else:
                    await callback.message.edit_text(result_text, parse_mode='HTML')
                # Очищаем состояние поиска и progress_message_id
                self.db_manager.clear_search_state(user_id)
            else:
                error_text = self.format_progress_message(search_state) + '\n❌ Ошибка при создании подписки'
                if search_state.progress_message_id:
                    await self.notification_service.edit_message(
                        callback.message.chat.id,
                        search_state.progress_message_id,
                        error_text,
                        parse_mode='HTML'
                    )
                else:
                    await callback.message.edit_text(error_text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Ошибка создания подписки на поезд: {e}")
            error_text = self.format_progress_message(search_state) + '\n❌ Ошибка при создании подписки'
            if search_state and search_state.progress_message_id:
                await self.notification_service.edit_message(
                    callback.message.chat.id,
                    search_state.progress_message_id,
                    error_text,
                    parse_mode='HTML'
                )
            else:
                await callback.message.edit_text(error_text, parse_mode='HTML')
    
    async def subscribe_to_search(self, callback: CallbackQuery):
        """Подписка на отслеживание"""
        try:
            user_id = callback.from_user.id
            search_state = self.db_manager.get_search_state(user_id)
            
            if not search_state or not all([
                search_state.origin_code, 
                search_state.destination_code, 
                search_state.departure_date
            ]):
                await callback.message.edit_text("❌ Не все параметры поиска заполнены")
                return
            
            # Создаем подписку
            subscription = Subscription(
                id=None,
                user_id=user_id,
                origin_code=search_state.origin_code,
                origin_name=search_state.origin_name,
                destination_code=search_state.destination_code,
                destination_name=search_state.destination_name,
                departure_date=search_state.departure_date,
                train_numbers=search_state.train_numbers,
                car_types=search_state.car_types,
                min_seats=search_state.min_seats,
                adult_passengers=search_state.adult_passengers,
                children_passengers=search_state.children_passengers,
                interval_minutes=5,
                is_active=True,
                created_at=datetime.now()
            )
            
            subscription_id = self.db_manager.create_subscription(subscription)
            
            if subscription_id:
                await callback.message.edit_text(
                    f"✅ Подписка создана!\n\n"
                    f"Маршрут: {search_state.origin_name} -> {search_state.destination_name}\n"
                    f"Дата: {search_state.departure_date[:10]}\n\n"
                    f"Бот будет проверять наличие мест каждые 5 минут и уведомит вас при их появлении."
                )
                
                # Очищаем состояние поиска
                self.db_manager.clear_search_state(user_id)
            else:
                await callback.message.edit_text("❌ Ошибка при создании подписки")
                
        except Exception as e:
            logger.error(f"Ошибка создания подписки: {e}")
            await callback.message.edit_text("❌ Ошибка при создании подписки")
    
    async def disable_subscription(self, callback: CallbackQuery):
        """Отключение подписки"""
        try:
            data = callback.data
            user_id = callback.from_user.id
            
            # Извлекаем ID подписки
            subscription_id = int(data.split("_")[-1])
            
            # Отключаем подписку
            success = self.db_manager.disable_subscription(subscription_id, user_id)
            
            if success:
                await callback.message.edit_text("✅ Подписка отключена!")
            else:
                await callback.message.edit_text("❌ Подписка не найдена или уже отключена.")
                
        except Exception as e:
            logger.error(f"Ошибка отключения подписки: {e}")
            await callback.message.edit_text("❌ Ошибка при отключении подписки")

    async def confirm_delete_subscription(self, callback: CallbackQuery):
        """Шаг подтверждения удаления подписки (отдельным сообщением)."""
        try:
            subscription_id = int(callback.data.split("_")[-1])
            keyboard = [[
                {"text": "🗑 Да, удалить", "callback_data": f"dodelsub_{subscription_id}", "style": "danger"},
                {"text": "↩️ Отмена", "callback_data": "canceldel", "style": "primary"},
            ]]
            await self.notification_service.send_message(
                callback.from_user.id,
                f"Удалить подписку #{subscription_id} безвозвратно?",
                keyboard=keyboard,
            )
            await callback.answer()
        except Exception as e:
            logger.error(f"Ошибка подтверждения удаления: {e}")
            await callback.answer("❌ Ошибка")

    async def cancel_delete_subscription(self, callback: CallbackQuery):
        """Отмена удаления — убираем сообщение-подтверждение."""
        try:
            await self.notification_service.delete_message(
                callback.message.chat.id, callback.message.message_id
            )
            await callback.answer("Отменено")
        except Exception as e:
            logger.error(f"Ошибка отмены удаления: {e}")
            await callback.answer()

    async def delete_subscription(self, callback: CallbackQuery):
        """Удаление подписки после подтверждения."""
        try:
            user_id = callback.from_user.id
            subscription_id = int(callback.data.split("_")[-1])
            success = self.db_manager.delete_subscription(subscription_id, user_id)
            text = f"🗑 Подписка #{subscription_id} удалена." if success else "❌ Подписка не найдена."
            await callback.message.edit_text(text)
            await callback.answer("Удалено" if success else "Не найдено")
        except Exception as e:
            logger.error(f"Ошибка удаления подписки: {e}")
            await callback.answer("❌ Ошибка")

    async def enable_subscription(self, callback: CallbackQuery):
        """Включение подписки"""
        try:
            data = callback.data
            user_id = callback.from_user.id

            subscription_id = int(data.split("_")[-1])
            success = self.db_manager.enable_subscription(subscription_id, user_id)

            if success:
                await callback.message.edit_text("✅ Подписка включена!")
            else:
                await callback.message.edit_text("❌ Подписка не найдена или уже активна.")

        except Exception as e:
            logger.error(f"Ошибка включения подписки: {e}")
            await callback.message.edit_text("❌ Ошибка при включении подписки")
    
    async def check_subscription_now(self, callback: CallbackQuery):
        """Мгновенная проверка наличия мест по подписке (кнопка «Проверить сейчас»)"""
        try:
            user_id = callback.from_user.id
            subscription_id = int(callback.data.split("_")[-1])
            subscription = self.db_manager.get_subscription(subscription_id, user_id)
            if not subscription:
                await callback.answer("Подписка не найдена")
                return
            await callback.answer("Проверяю наличие мест…")

            trains_data = await asyncio.to_thread(
                self.rzd_api.search_trains,
                origin_code=subscription.origin_code,
                destination_code=subscription.destination_code,
                departure_date=subscription.departure_date,
                adult_passengers=subscription.adult_passengers,
                children_passengers=subscription.children_passengers,
            )
            allowed = subscription.train_numbers.split(',') if subscription.train_numbers else None
            car_types = [c for c in (subscription.car_types or '').split(',') if c]
            berth = subscription.berth
            max_price = subscription.max_price
            lines = []
            unit = flt.matched_unit(berth)
            from services.rzd_seatmap import SeatMapService, SEATMAP_BERTHS as seatmap_berths, format_seatmap_detail
            for train in trains_data.get('trains', []):
                t = self.rzd_api.extract_train_info(train)
                if allowed and t['number'] not in allowed:
                    continue
                duration = f" ({t['duration']})" if t['duration'] else ''
                line = f"🚂 <b>{t['number']}</b> {t['name']} {t['departure']}→{t['arrival']}{duration}\n"
                if berth in seatmap_berths:
                    # точный список купе через схему вагонов (сетевой запрос — в поток)
                    detail = await asyncio.to_thread(
                        SeatMapService().detail_for_berth, berth,
                        subscription.origin_code, subscription.destination_code,
                        train.get('LocalDepartureDateTime'),
                        train.get('TrainNumber') or train.get('DisplayTrainNumber') or '',
                        train.get('Provider', 'P1'),
                    )
                    if detail:
                        line += f"   ✅ {unit}: {len(detail)}\n   🚪 {format_seatmap_detail(berth, detail)}"
                    else:
                        line += f"   ❌ нет ({unit})"
                else:
                    seats = self.rzd_api.match_seats(
                        train, car_types=car_types or None, berth=berth, max_price=max_price
                    )
                    if seats['total'] > 0:
                        line += f"   ✅ {unit}: {seats['total']}"
                        if seats['lower'] or seats['upper']:
                            line += f" (низ {seats['lower']} / верх {seats['upper']})"
                        if seats['min_price']:
                            line += f" · от {seats['min_price']:.0f} ₽"
                    else:
                        line += f"   ❌ нет ({unit})"
                lines.append(line)

            summary = flt.format_filter_summary(subscription.car_types, berth, max_price)
            header = (
                f"🔄 Текущее наличие по подписке #{subscription.id}\n"
                f"{subscription.origin_name} → {subscription.destination_name}, "
                f"{subscription.departure_date[:10]}\n"
                f"Фильтр: {summary}\n\n"
            )
            body = "\n".join(lines) if lines else "Поезда не найдены."
            url = await asyncio.to_thread(
                self.rzd_api.build_purchase_url,
                subscription.origin_code, subscription.destination_code, subscription.departure_date,
                subscription.origin_name, subscription.destination_name, subscription.adult_passengers,
            )
            keyboard = [[{"text": "🎫 Купить на РЖД", "url": url, "style": "success"}]]
            await self.notification_service.send_message(user_id, header + body, keyboard=keyboard)
        except Exception as e:
            logger.error(f"Ошибка мгновенной проверки подписки: {e}")
            await callback.answer("❌ Ошибка при проверке")

    async def handle_select_train(self, callback: CallbackQuery):
        """Выбор поезда -> показываем панель наличия и фильтров"""
        try:
            data = callback.data
            user_id = callback.from_user.id
            parts = data.split('_', 3)
            if len(parts) < 3:
                await callback.answer('❌ Ошибка при выборе поезда')
                return
            train_number = parts[2]
            train_info = parts[3] if len(parts) > 3 else train_number
            search_state = self.db_manager.get_search_state(user_id)
            if not search_state:
                await callback.answer('❌ Ошибка состояния поиска')
                return
            await callback.answer("Загружаю наличие…")
            trains_data = await asyncio.to_thread(
                self.rzd_api.search_trains,
                origin_code=search_state.origin_code,
                destination_code=search_state.destination_code,
                departure_date=search_state.departure_date,
                adult_passengers=search_state.adult_passengers,
                children_passengers=search_state.children_passengers,
            )
            selected = None
            for tr in trains_data.get('trains', []):
                if self.rzd_api.extract_train_info(tr)['number'] == train_number:
                    selected = tr
                    break
            search_state.selected_train_number = train_number
            search_state.selected_train_info = train_info
            search_state.search_step = 'done'
            search_state.selected_train_cargroups = self._store_train(selected or {})
            search_state.filter_car_types = ''
            search_state.filter_berth = 'any'
            search_state.filter_max_price = 0
            search_state.editing_subscription_id = None
            self.db_manager.save_search_state(search_state)
            await self._render_filter_panel(callback.message.chat.id, search_state)
        except Exception as e:
            logger.error(f'Ошибка выбора поезда: {e}')
            await callback.answer('❌ Ошибка при выборе поезда')

    @staticmethod
    def _store_train(train: dict) -> str:
        """Сериализует нужные для панели данные поезда: CarGroups + мета (provider, dep)."""
        return json.dumps({
            "cg": train.get("CarGroups", []),
            "p": train.get("Provider", "P1"),
            "d": train.get("LocalDepartureDateTime"),
        }, ensure_ascii=False)

    @staticmethod
    def _load_train(blob: str):
        """Возвращает (cargroups, provider, dep). Поддерживает старый формат (список CarGroups)."""
        try:
            data = json.loads(blob or '[]')
        except Exception:
            return [], "P1", None
        if isinstance(data, list):  # старый формат — только CarGroups
            return data, "P1", None
        return data.get("cg", []), data.get("p", "P1"), data.get("d")

    async def _render_filter_panel(self, chat_id: int, search_state: SearchState):
        """Рисует/обновляет панель наличия и фильтров (edit-in-place)."""
        cargroups, provider, dep = self._load_train(search_state.selected_train_cargroups)
        train = {'CarGroups': cargroups}
        car_types = [c for c in (search_state.filter_car_types or '').split(',') if c]
        breakdown = self.rzd_api.match_seats(train)
        from services.rzd_seatmap import SeatMapService, SEATMAP_BERTHS
        if search_state.filter_berth in SEATMAP_BERTHS:
            # точный подсчёт купе через схему вагонов (сетевой запрос — в поток)
            n = await asyncio.to_thread(
                SeatMapService().count_for_berth, search_state.filter_berth,
                search_state.origin_code, search_state.destination_code, dep,
                search_state.selected_train_number, provider,
            )
            matched = {'total': n if n is not None else 0}
        else:
            matched = self.rzd_api.match_seats(
                train, car_types=car_types or None,
                berth=search_state.filter_berth, max_price=search_state.filter_max_price,
            )
        summary = flt.format_filter_summary(
            search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price
        )
        text = self._panel_text(breakdown, matched, summary,
                                matched_unit=flt.matched_unit(search_state.filter_berth))
        if search_state.editing_subscription_id:
            submit_text, submit_cb = "💾 Сохранить фильтры", "save_filters"
        else:
            submit_text, submit_cb = "🔔 Подписаться", "subscribe_filtered"
        context = flt.build_filter_context(cargroups)
        keyboard = flt.build_filter_keyboard(
            search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price,
            context, submit_text=submit_text, submit_cb=submit_cb,
        )
        if search_state.progress_message_id:
            await self.notification_service.edit_message(
                chat_id, search_state.progress_message_id, text, keyboard=keyboard, parse_mode='HTML'
            )
        else:
            sent_id = await self.notification_service.send_message_with_keyboard(chat_id, text, keyboard)
            if sent_id:
                search_state.progress_message_id = sent_id
                self.db_manager.save_search_state(search_state)

    async def handle_filter_toggle(self, callback: CallbackQuery):
        """Тоггл фильтра: обновляем состояние и перерисовываем панель без запроса к РЖД."""
        try:
            user_id = callback.from_user.id
            parsed = flt.parse_filter_callback(callback.data)
            search_state = self.db_manager.get_search_state(user_id)
            if not parsed or not search_state:
                await callback.answer()
                return
            kind, value = parsed
            if kind == 'car':
                search_state.filter_car_types = flt.toggle_car_type(search_state.filter_car_types, value)
            elif kind == 'berth':
                search_state.filter_berth = value
            elif kind == 'price':
                # ползунок ±: считаем потолок из диапазона цен выбранного поезда
                cargroups, _, _ = self._load_train(search_state.selected_train_cargroups)
                ctx = flt.build_filter_context(cargroups)
                search_state.filter_max_price = flt.adjust_price(
                    search_state.filter_max_price, value, ctx['price_min'], ctx['price_max']
                )
            self.db_manager.save_search_state(search_state)
            await self._render_filter_panel(callback.message.chat.id, search_state)
            await callback.answer()
        except Exception as e:
            logger.error(f"Ошибка тоггла фильтра: {e}")
            await callback.answer()

    async def handle_edit_filters(self, callback: CallbackQuery):
        """Открывает панель фильтров для существующей подписки (режим правки)."""
        try:
            user_id = callback.from_user.id
            subscription_id = int(callback.data.split("_")[-1])
            sub = self.db_manager.get_subscription(subscription_id, user_id)
            if not sub:
                await callback.answer("Подписка не найдена")
                return
            await callback.answer("Загружаю фильтры…")
            trains_data = await asyncio.to_thread(
                self.rzd_api.search_trains,
                origin_code=sub.origin_code,
                destination_code=sub.destination_code,
                departure_date=sub.departure_date,
                adult_passengers=sub.adult_passengers,
                children_passengers=sub.children_passengers,
            )
            allowed = sub.train_numbers.split(',') if sub.train_numbers else None
            selected = {}
            for tr in trains_data.get('trains', []):
                num = self.rzd_api.extract_train_info(tr)['number']
                if allowed and num not in allowed:
                    continue
                selected = tr
                break
            search_state = self.db_manager.get_search_state(user_id) or SearchState(user_id=user_id)
            # переносим контекст подписки в состояние, чтобы панель работала как при создании
            search_state.origin_code = sub.origin_code
            search_state.origin_name = sub.origin_name
            search_state.destination_code = sub.destination_code
            search_state.destination_name = sub.destination_name
            search_state.departure_date = sub.departure_date
            search_state.selected_train_number = sub.train_numbers
            search_state.selected_train_cargroups = self._store_train(selected)
            search_state.filter_car_types = sub.car_types or ''
            search_state.filter_berth = sub.berth or 'any'
            search_state.filter_max_price = sub.max_price or 0
            search_state.editing_subscription_id = subscription_id
            search_state.search_step = 'editfilters'
            search_state.progress_message_id = None  # рисуем панель отдельным сообщением
            self.db_manager.save_search_state(search_state)
            await self._render_filter_panel(callback.message.chat.id, search_state)
        except Exception as e:
            logger.error(f"Ошибка открытия правки фильтров: {e}")
            await callback.answer("❌ Ошибка")

    async def save_subscription_filters(self, callback: CallbackQuery):
        """Сохраняет изменённые фильтры в существующую подписку."""
        try:
            user_id = callback.from_user.id
            search_state = self.db_manager.get_search_state(user_id)
            if not search_state or not search_state.editing_subscription_id:
                await callback.answer("Нет подписки для сохранения")
                return
            sub_id = search_state.editing_subscription_id
            ok = self.db_manager.update_subscription_filters(
                sub_id, user_id,
                search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price,
            )
            summary = flt.format_filter_summary(
                search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price
            )
            if ok:
                text = (f"✅ Фильтры подписки #{sub_id} обновлены.\nФильтр: <b>{summary}</b>")
            else:
                text = "❌ Не удалось обновить фильтры подписки."
            if search_state.progress_message_id:
                await self.notification_service.edit_message(
                    callback.message.chat.id, search_state.progress_message_id, text, parse_mode='HTML'
                )
            else:
                await callback.message.answer(text, parse_mode='HTML')
            self.db_manager.clear_search_state(user_id)
            await callback.answer("Сохранено")
        except Exception as e:
            logger.error(f"Ошибка сохранения фильтров подписки: {e}")
            await callback.answer("❌ Ошибка")

    async def subscribe_to_selected_train(self, callback: CallbackQuery):
        """Подписка на выбранный поезд (через этап выбора)"""
        try:
            user_id = callback.from_user.id
            search_state = self.db_manager.get_search_state(user_id)
            if not search_state or not all([
                search_state.origin_code,
                search_state.destination_code,
                search_state.departure_date,
                search_state.selected_train_number
            ]):
                progress_text = self.format_progress_message(search_state) + '\n❌ Не все параметры поиска заполнены'
                if search_state and search_state.progress_message_id:
                    await self.notification_service.edit_message(
                        callback.message.chat.id,
                        search_state.progress_message_id,
                        progress_text,
                        parse_mode='HTML'
                    )
                else:
                    await callback.message.edit_text(progress_text, parse_mode='HTML')
                return
            subscription = Subscription(
                id=None,
                user_id=user_id,
                origin_code=search_state.origin_code,
                origin_name=search_state.origin_name,
                destination_code=search_state.destination_code,
                destination_name=search_state.destination_name,
                departure_date=search_state.departure_date,
                train_numbers=search_state.selected_train_number,
                car_types=search_state.filter_car_types,
                berth=search_state.filter_berth,
                max_price=search_state.filter_max_price,
                min_seats=search_state.min_seats,
                adult_passengers=search_state.adult_passengers,
                children_passengers=search_state.children_passengers,
                interval_minutes=5,
                is_active=True,
                created_at=datetime.now()
            )
            subscription_id = self.db_manager.create_subscription(subscription)
            if subscription_id:
                result_text = (
                    f"✅ Подписка создана!\n\n"
                    f"Поезд: <b>{search_state.selected_train_number}</b> {search_state.selected_train_info or ''}\n"
                    f"Маршрут: {search_state.origin_name} -> {search_state.destination_name}\n"
                    f"Дата: {search_state.departure_date[:10]}\n"
                    f"Фильтр: {flt.format_filter_summary(search_state.filter_car_types, search_state.filter_berth, search_state.filter_max_price)}\n\n"
                    f"Бот будет проверять наличие мест в поезде {search_state.selected_train_number} каждые 5 минут и уведомит вас при их появлении."
                )
                if search_state.progress_message_id:
                    await self.notification_service.edit_message(
                        callback.message.chat.id,
                        search_state.progress_message_id,
                        result_text,
                        parse_mode='HTML'
                    )
                else:
                    await callback.message.edit_text(result_text, parse_mode='HTML')
                self.db_manager.clear_search_state(user_id)
            else:
                error_text = self.format_progress_message(search_state) + '\n❌ Ошибка при создании подписки'
                if search_state and search_state.progress_message_id:
                    await self.notification_service.edit_message(
                        callback.message.chat.id,
                        search_state.progress_message_id,
                        error_text,
                        parse_mode='HTML'
                    )
                else:
                    await callback.message.edit_text(error_text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Ошибка создания подписки на выбранный поезд: {e}")
            error_text = self.format_progress_message(search_state) + '\n❌ Ошибка при создании подписки'
            if search_state and search_state.progress_message_id:
                await self.notification_service.edit_message(
                    callback.message.chat.id,
                    search_state.progress_message_id,
                    error_text,
                    parse_mode='HTML'
                )
            else:
                await callback.message.edit_text(error_text, parse_mode='HTML')
    
    async def handle(self, event) -> None:
        """Обработка события"""
        pass
