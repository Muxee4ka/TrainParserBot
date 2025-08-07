#!/usr/bin/env python3
"""
Скрипт для установки зависимостей Telegram бота
"""

import subprocess
import sys

def install_requirements():
    """Установка зависимостей"""
    print("🔧 Установка зависимостей для Telegram бота...")
    
    requirements = [
        "python-telegram-bot==20.7",
        "requests==2.31.0"
    ]
    
    for package in requirements:
        print(f"📦 Устанавливаю {package}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✅ {package} установлен успешно")
        except subprocess.CalledProcessError as e:
            print(f"❌ Ошибка при установке {package}: {e}")
            return False
    
    print("\n✅ Все зависимости установлены!")
    return True

def check_dependencies():
    """Проверка установленных зависимостей"""
    print("🔍 Проверка зависимостей...")
    
    try:
        import telegram
        print("✅ python-telegram-bot установлен")
    except ImportError:
        print("❌ python-telegram-bot не установлен")
        return False
    
    try:
        import requests
        print("✅ requests установлен")
    except ImportError:
        print("❌ requests не установлен")
        return False
    
    return True

def main():
    """Главная функция"""
    print("🚆 Настройка Telegram бота для поиска поездов")
    print("=" * 50)
    
    # Устанавливаем зависимости
    if not install_requirements():
        print("❌ Ошибка при установке зависимостей")
        return
    
    # Проверяем установку
    if not check_dependencies():
        print("❌ Не все зависимости установлены")
        return
    
    print("\n🎉 Настройка завершена!")
    print("\n📋 Следующие шаги:")
    print("1. Получите токен бота у @BotFather")
    print("2. Замените YOUR_TELEGRAM_TOKEN_HERE в telegram_bot.py")
    print("3. Запустите бота: python telegram_bot.py")

if __name__ == "__main__":
    main()



