## 🚆 TrainParserBot

<div align="center">

  <a href="https://t.me/rzd_train_search_bot">
    <img alt="Telegram" src="https://img.shields.io/badge/Telegram-@rzd__train__search__bot-2CA5E0?logo=telegram" />
  </a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python" />
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green" />

</div>

Telegram-бот на aiogram для поиска поездов РЖД и подписки на уведомления о появлении мест. Поддерживает пошаговую настройку поиска в одном прогресс-сообщении, хранит состояние в SQLite и умеет присылать уведомления при появлении мест.

Ссылка на бота: [@rzd_train_search_bot](https://t.me/rzd_train_search_bot)

<details>
  <summary><b>Содержание</b></summary>

- [✨ Возможности](#-возможности)
- [🧱 Архитектура](#-архитектура)
- [⚙️ Требования](#-требования)
- [🚀 Установка](#-установка)
- [🧪 Тесты](#-тесты)
- [🛠️ CI](#-ci)
- [📎 Полезные файлы](#-полезные-файлы)
- [🧭 Примечания по UX](#-примечания-по-ux)
- [📄 Лицензия](#-лицензия)

</details>

### ✨ Возможности
- **Пошаговый поиск**: выбор станции отправления → назначения → даты → поезда
- **Аккуратный интерфейс**: всегда одно прогресс-сообщение, лишние сообщения удаляются
- **Подписки**: мониторинг наличия мест с заданным интервалом, уведомления в Telegram
- **SQLite**: хранение подписок и состояния пользователя
- **Готовность к CI**: GitHub Actions для автозапуска тестов

> 💡 Подсказка: бот поддерживает как быстрый разовый поиск, так и длительные мониторинги с уведомлениями о появлении мест.

### 🧱 Архитектура
- `bot.py`: точка входа; инициализация aiogram, роутеров и мониторинга
- `handlers/`: обработчики команд (`CommandsHandler`) и поиска (`SearchHandler`)
- `services/`: интеграции с внешними сервисами
  - `rzd_api.py`: работа с публичными API РЖД
  - `notification.py`: отправка/редактирование/удаление сообщений Telegram Bot API
  - `monitoring.py`: периодическая проверка активных подписок
- `database/`: модели (`models.py`) и менеджер БД (`manager.py`)
- `config.py`: конфигурация через .env (python-dotenv) с дефолтами
- `tests/`: pytest (unit + integration)

### ⚙️ Требования
- Python 3.10+
- Зависимости из `requirements.txt`:
  - aiogram, aiohttp, requests, python-dotenv, pytest

### 🚀 Установка
1) Установите зависимости
```
python -m pip install -r requirements.txt
```

2) Создайте файл `.env` в корне (или выполните `python setup.py`, он создаст шаблон)
```
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
DATABASE_PATH=data/train_subscriptions.db
```
Дополнительно поддерживаются переменные (опционально):
- `MONITORING_INTERVAL` (по умолчанию 300)
- `MAX_MESSAGE_LENGTH` (4000)
- `MAX_CALLBACK_DATA_LENGTH` (64)
- `MAX_STATIONS_PER_SEARCH` (10)
- `MIN_QUERY_LENGTH` (2)
- `MAX_TRAINS_PER_RESULT` (10)
- `RZD_API_URL`, `RZD_SUGGEST_URL`, `USER_AGENT`

3) Запуск бота
```
python bot.py
```

> ⚠️ Важно: для работы интеграционных тестов требуется доступ к публичным API РЖД; они отключены по умолчанию.

### 🧪 Тесты
- Юнит-тесты:
```
pytest
```
- Интеграционные тесты (выполняют реальные запросы к API РЖД) отключены по умолчанию. Чтобы включить:
```
RUN_INTEGRATION_TESTS=1 pytest
```

### 🛠️ CI
- GitHub Actions: `.github/workflows/ci.yml`
  - Устанавливает зависимости
  - Создает `.env` с `BOT_TOKEN` из Secrets
  - Запускает `pytest` (интеграционные отключены)

### 📎 Полезные файлы
- Быстрый старт: `QUICK_START.md`
- Сводка проекта: `PROJECT_SUMMARY.md`

### 🧭 Примечания по UX
- При каждом выборе/вводе бот удаляет сообщения пользователя и варианты, оставляя одно прогресс-сообщение с текущим состоянием и следующей подсказкой
- Если в callback приходит только код станции, бот подставляет корректное название по коду через API

### 📄 Лицензия
MIT (по умолчанию). При необходимости добавьте файл LICENSE и обновите раздел.



