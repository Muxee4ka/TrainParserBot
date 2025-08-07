# 🚀 Быстрый старт

## 1) Установка зависимостей
```bash
python -m pip install -r requirements.txt
```

## 2) Настройка окружения
Создайте `.env` в корне (или запустите `python setup.py`, он создаст шаблон):
```
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
DATABASE_PATH=data/train_subscriptions.db
```

## 3) Запуск бота
```bash
python bot.py
```

## 4) Тесты
- Юнит-тесты:
```bash
pytest
```
- Интеграционные тесты (включить явно):
```bash
RUN_INTEGRATION_TESTS=1 pytest
```

## 5) Структура
```
TrainParserBot/
├── bot.py                # Точка входа aiogram
├── handlers/             # Хендлеры команд и поиска
├── services/             # RZD API, уведомления, мониторинг
├── database/             # Модели и менеджер БД
├── tests/                # pytest (unit + integration)
├── config.py             # Конфиг с .env
├── requirements.txt      # Зависимости
├── setup.py              # Установка deps, .env, запуск тестов
├── .github/workflows/ci.yml # GitHub Actions
└── .env                  # Переменные окружения
```

## 6) Примечания
- Все лишние сообщения при настройке поиска удаляются — остаётся только прогресс-сообщение
- Названия станций корректно подставляются даже если в callback пришёл только код




