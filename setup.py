#!/usr/bin/env python3
"""
Скрипт для установки зависимостей и запуска тестов
"""

import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
REQ = os.path.join(ROOT, "requirements.txt")


def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    return subprocess.call(cmd)


def install_requirements() -> bool:
    print("🔧 Установка зависимостей из requirements.txt...")
    if not os.path.exists(REQ):
        print("❌ requirements.txt не найден")
        return False
    code = run([sys.executable, "-m", "pip", "install", "-r", REQ])
    if code != 0:
        print("❌ Ошибка установки зависимостей")
        return False
    print("✅ Зависимости установлены")
    return True


def ensure_env_file() -> None:
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        print("ℹ️ .env уже существует")
        return
    print("📝 Создаю .env (пустой шаблон)...")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("BOT_TOKEN=\n")
        f.write("DATABASE_PATH=data/train_subscriptions.db\n")


def run_tests() -> bool:
    print("🧪 Запуск тестов...")
    code = run([sys.executable, "-m", "pytest", "-q"])
    if code != 0:
        print("❌ Тесты не прошли")
        return False
    print("✅ Все тесты пройдены")
    return True


def main():
    print("🚆 Настройка проекта TrainParserBot")
    print("=" * 60)

    if not install_requirements():
        sys.exit(1)

    ensure_env_file()

    # Создать директорию для данных
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)

    # Запуск тестов (опционально)
    run_tests()

    print("\n🎉 Готово! Основные команды:")
    print("- Запуск бота: python bot.py")
    print("- Запуск тестов: pytest")


if __name__ == "__main__":
    main()




