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
    
    async def send_message(self, user_id: int, text: str, parse_mode: str = "HTML") -> bool:
        """Отправка сообщения пользователю"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "chat_id": user_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
                
                async with session.post(f"{self.api_url}/sendMessage", data=data) as response:
                    if response.status == 200:
                        logger.info(f"Сообщение отправлено пользователю {user_id}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"Ошибка отправки сообщения: {response.status} - {response_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            return False
    
    async def send_message_with_keyboard(self, user_id: int, text: str, 
                                       keyboard: list, parse_mode: str = "HTML") -> bool:
        """Отправка сообщения с клавиатурой"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "chat_id": user_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "reply_markup": {
                        "inline_keyboard": keyboard
                    }
                }
                
                async with session.post(f"{self.api_url}/sendMessage", json=data) as response:
                    if response.status == 200:
                        logger.info(f"Сообщение с клавиатурой отправлено пользователю {user_id}")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"Ошибка отправки сообщения с клавиатурой: {response.status} - {response_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения с клавиатурой: {e}")
            return False
    
    async def edit_message(self, chat_id: int, message_id: int, text: str, 
                          keyboard: Optional[list] = None, parse_mode: str = "HTML") -> bool:
        """Редактирование сообщения"""
        try:
            async with aiohttp.ClientSession() as session:
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
            async with aiohttp.ClientSession() as session:
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



