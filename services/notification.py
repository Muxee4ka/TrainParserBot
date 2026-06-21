"""
Сервис уведомлений
"""
import aiohttp
import logging
from typing import Optional

from config import config

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис отправки уведомлений"""
    
    def __init__(self):
        self.bot_token = config.BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Лениво создаёт и переиспользует одну ClientSession на весь срок жизни сервиса"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Закрытие сессии (при остановке бота)"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_message(self, user_id: int, text: str, keyboard: Optional[list] = None,
                           parse_mode: str = "HTML") -> Optional[int]:
        """Отправка сообщения пользователю. Возвращает message_id или None"""
        try:
            session = await self._get_session()
            data = {
                "chat_id": user_id,
                "text": text,
                "parse_mode": parse_mode
            }
            if keyboard:
                data["reply_markup"] = {"inline_keyboard": keyboard}

            async with session.post(f"{self.api_url}/sendMessage", json=data) as response:
                if response.status == 200:
                    logger.info(f"Сообщение отправлено пользователю {user_id}")
                    payload = await response.json()
                    return payload.get("result", {}).get("message_id")
                else:
                    response_text = await response.text()
                    logger.error(f"Ошибка отправки сообщения: {response.status} - {response_text}")
                    return None

        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            return None

    async def send_message_with_keyboard(self, user_id: int, text: str,
                                       keyboard: list, parse_mode: str = "HTML") -> Optional[int]:
        """Отправка сообщения с клавиатурой. Возвращает message_id или None"""
        return await self.send_message(user_id, text, keyboard=keyboard, parse_mode=parse_mode)
    
    async def edit_message(self, chat_id: int, message_id: int, text: str, 
                          keyboard: Optional[list] = None, parse_mode: str = "HTML") -> bool:
        """Редактирование сообщения"""
        try:
            session = await self._get_session()
            data = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": parse_mode
            }

            if keyboard:
                data["reply_markup"] = {"inline_keyboard": keyboard}

            async with session.post(f"{self.api_url}/editMessageText", json=data) as response:
                if response.status == 200:
                    logger.info(f"Сообщение отредактировано")
                    return True
                else:
                    response_text = await response.text()
                    logger.error(f"Ошибка редактирования сообщения: {response.status} - {response_text}")
                    return False

        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            return False
    
    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> bool:
        """Ответ на callback query"""
        try:
            session = await self._get_session()
            data = {
                "callback_query_id": callback_query_id
            }

            if text:
                data["text"] = text

            async with session.post(f"{self.api_url}/answerCallbackQuery", data=data) as response:
                if response.status == 200:
                    return True
                else:
                    response_text = await response.text()
                    logger.error(f"Ошибка ответа на callback: {response.status} - {response_text}")
                    return False

        except Exception as e:
            logger.error(f"Ошибка при ответе на callback: {e}")
            return False

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        """Удаление сообщения"""
        try:
            session = await self._get_session()
            data = {
                "chat_id": chat_id,
                "message_id": message_id
            }
            async with session.post(f"{self.api_url}/deleteMessage", data=data) as response:
                if response.status == 200:
                    logger.info(f"Сообщение {message_id} удалено в чате {chat_id}")
                    return True
                else:
                    response_text = await response.text()
                    logger.error(f"Ошибка удаления сообщения: {response.status} - {response_text}")
                    return False
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения: {e}")
            return False



