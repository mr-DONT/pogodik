import os
import logging
from datetime import datetime
from typing import Optional

import requests
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')

# ID городов для OpenWeatherMap
CITIES = {
    'Севастополь': {'lat': 44.6167, 'lon': 33.5254},
    'Симферополь': {'lat': 44.9572, 'lon': 34.1108}
}


# Клавиатура с кнопками
def get_main_keyboard():
    """Основная клавиатура с кнопками"""
    keyboard = [
        [KeyboardButton("🌤️ Севастополь"), KeyboardButton("🌤️ Симферополь")],
        [KeyboardButton("📅 Прогноз на день")],
        [KeyboardButton("⚙️ Настроить рассылку"), KeyboardButton("🆘 Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_forecast_keyboard():
    """Клавиатура для выбора города прогноза"""
    keyboard = [
        [KeyboardButton("📅 Севастополь прогноз"), KeyboardButton("📅 Симферополь прогноз")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_schedule_keyboard():
    """Клавиатура для настройки рассылки"""
    keyboard = [
        [KeyboardButton("⏰ Севастополь в 8:00"), KeyboardButton("⏰ Симферополь в 8:00")],
        [KeyboardButton("⏰ Оба города в 9:00"), KeyboardButton("⏰ Оба города в 12:00")],
        [KeyboardButton("❌ Остановить рассылку"), KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# Класс для работы с погодой
class WeatherService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "http://api.openweathermap.org/data/2.5/weather"
        self.forecast_url = "http://api.openweathermap.org/data/2.5/forecast"

    def get_current_weather(self, city_name: str) -> Optional[dict]:
        """Получение текущей погоды для города"""
        try:
            city_data = CITIES.get(city_name)
            if not city_data:
                return None

            params = {
                'lat': city_data['lat'],
                'lon': city_data['lon'],
                'appid': self.api_key,
                'units': 'metric',
                'lang': 'ru'
            }

            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            return self._format_weather_data(data, city_name)

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при получении погоды: {e}")
            return None

    def get_daily_forecast(self, city_name: str) -> Optional[str]:
        """Получение прогноза на день"""
        try:
            city_data = CITIES.get(city_name)
            if not city_data:
                return None

            params = {
                'lat': city_data['lat'],
                'lon': city_data['lon'],
                'appid': self.api_key,
                'units': 'metric',
                'lang': 'ru',
                'cnt': 8  # 8 периодов = 24 часа
            }

            response = requests.get(self.forecast_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            return self._format_forecast_data(data, city_name)

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка при получении прогноза: {e}")
            return None

    def _format_weather_data(self, data: dict, city_name: str) -> dict:
        """Форматирование данных о погоде"""
        main = data['main']
        weather = data['weather'][0]
        wind = data['wind']

        return {
            'city': city_name,
            'temperature': round(main['temp']),
            'feels_like': round(main['feels_like']),
            'description': weather['description'].capitalize(),
            'humidity': main['humidity'],
            'pressure': round(main['pressure'] * 0.750062),
            'wind_speed': wind['speed'],
            'wind_gust': wind.get('gust', 0),
            'icon': weather['icon'],
            'timestamp': datetime.fromtimestamp(data['dt'])
        }

    def _format_forecast_data(self, data: dict, city_name: str) -> str:
        """Форматирование прогноза"""
        forecast_text = f"📅 Прогноз погоды в {city_name} на 24 часа:\n\n"

        for item in data['list'][::2]:  # Каждые 6 часов
            time_str = datetime.fromtimestamp(item['dt']).strftime('%H:%M')
            temp = round(item['main']['temp'])
            desc = item['weather'][0]['description'].capitalize()

            forecast_text += f"🕐 {time_str}: {temp}°C, {desc}\n"

        return forecast_text


# Инициализация сервиса погоды
weather_service = WeatherService(OPENWEATHER_API_KEY)


# Функции бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = """
🌤️ Добро пожаловать в бот погоды!

Выберите действие с помощью кнопок ниже:

• Нажмите на город для получения текущей погоды
• Нажмите "Прогноз на день" для прогноза
• Настройте ежедневную рассылку в "Настроить рассылку"

Доступные города: Севастополь и Симферополь
    """

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды помощи"""
    help_text = """
📋 Как пользоваться ботом:

1. **Текущая погода:**
   - Нажмите кнопку "🌤️ Севастополь" или "🌤️ Симферополь"

2. **Прогноз на день:**
   - Нажмите "📅 Прогноз на день"
   - Выберите город для прогноза

3. **Ежедневная рассылка:**
   - Нажмите "⚙️ Настроить рассылку"
   - Выберите время и город
   - Бот будет присылать погоду автоматически

4. **Остановка рассылки:**
   - В меню рассылки нажмите "❌ Остановить рассылку"

5. **Команды:**
   - /start - Перезапустить бота
   - /weather - Получить погоду (текстовый ввод)
   - /forecast - Получить прогноз
   - /help - Эта справка

Примеры текстовых команд:
/weather Севастополь
/forecast Симферополь
    """

    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений и нажатий кнопок"""
    message_text = update.message.text
    user = update.message.from_user

    logger.info(f"Пользователь {user.first_name} отправил: {message_text}")

    # Обработка кнопок с погодой
    if message_text == "🌤️ Севастополь":
        await send_weather(update, "Севастополь")

    elif message_text == "🌤️ Симферополь":
        await send_weather(update, "Симферополь")

    # Обработка прогноза
    elif message_text == "📅 Прогноз на день":
        await update.message.reply_text(
            "Выберите город для прогноза на 24 часа:",
            reply_markup=get_forecast_keyboard()
        )

    elif message_text == "📅 Севастополь прогноз":
        await send_forecast(update, "Севастополь")

    elif message_text == "📅 Симферополь прогноз":
        await send_forecast(update, "Симферополь")

    # Обработка рассылки
    elif message_text == "⚙️ Настроить рассылку":
        await update.message.reply_text(
            "⏰ Настройте ежедневную рассылку погоды:\n\n"
            "Выберите готовый вариант или используйте команду:\n"
            "/schedule <час> <минута> <город>\n\n"
            "Пример: /schedule 8 0 Севастополь",
            reply_markup=get_schedule_keyboard()
        )

    elif message_text == "⏰ Севастополь в 8:00":
        await setup_schedule(update, 8, 0, "Севастополь")

    elif message_text == "⏰ Симферополь в 8:00":
        await setup_schedule(update, 8, 0, "Симферополь")

    elif message_text == "⏰ Оба города в 9:00":
        await setup_schedule(update, 9, 0, "Оба")

    elif message_text == "⏰ Оба города в 12:00":
        await setup_schedule(update, 12, 0, "Оба")

    elif message_text == "❌ Остановить рассылку":
        await stop_schedule_command(update, context)

    # Навигация
    elif message_text == "⬅️ Назад":
        await update.message.reply_text(
            "Главное меню:",
            reply_markup=get_main_keyboard()
        )

    # Обработка текстовой команды /weather
    elif message_text.startswith("/weather"):
        if len(message_text.split()) > 1:
            city = message_text.split()[1]
            await send_weather(update, city)
        else:
            await update.message.reply_text(
                "Укажите город: /weather Севастополь",
                reply_markup=get_main_keyboard()
            )

    # Обработка текстовой команды /forecast
    elif message_text.startswith("/forecast"):
        if len(message_text.split()) > 1:
            city = message_text.split()[1]
            await send_forecast(update, city)
        else:
            await update.message.reply_text(
                "Укажите город: /forecast Севастополь",
                reply_markup=get_main_keyboard()
            )

    else:
        # Если сообщение не распознано, показываем главное меню
        await update.message.reply_text(
            "Используйте кнопки для навигации или команды:\n"
            "/start - Главное меню\n"
            "/help - Помощь",
            reply_markup=get_main_keyboard()
        )


async def send_weather(update: Update, city_name: str):
    """Отправка погоды для указанного города"""
    city_name = city_name.capitalize()

    if city_name not in CITIES:
        await update.message.reply_text(
            "Доступные города: Севастополь, Симферополь",
            reply_markup=get_main_keyboard()
        )
        return

    await update.message.reply_chat_action(action="typing")

    weather_data = weather_service.get_current_weather(city_name)

    if weather_data:
        message = format_weather_message(weather_data)
        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "Не удалось получить данные о погоде. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )


async def send_forecast(update: Update, city_name: str):
    """Отправка прогноза для указанного города"""
    city_name = city_name.replace(" прогноз", "").capitalize()

    if city_name not in CITIES:
        await update.message.reply_text(
            "Доступные города: Севастополь, Симферополь",
            reply_markup=get_forecast_keyboard()
        )
        return

    await update.message.reply_chat_action(action="typing")

    forecast = weather_service.get_daily_forecast(city_name)

    if forecast:
        await update.message.reply_text(
            forecast,
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "Не удалось получить прогноз. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )


def format_weather_message(weather_data: dict) -> str:
    """Форматирование сообщения с погодой"""
    emoji_map = {
        '01': '☀️',  # ясно
        '02': '⛅',  # малооблачно
        '03': '☁️',  # облачно
        '04': '☁️',  # пасмурно
        '09': '🌧️',  # дождь
        '10': '🌦️',  # дождь с солнцем
        '11': '⛈️',  # гроза
        '13': '❄️',  # снег
        '50': '🌫️',  # туман
    }

    icon = weather_data['icon'][:2]
    emoji = emoji_map.get(icon, '🌡️')

    return f"""
{emoji} <b>Погода в {weather_data['city']}</b>
📅 {weather_data['timestamp'].strftime('%d.%m.%Y %H:%M')}

🌡️ Температура: <b>{weather_data['temperature']}°C</b>
🤔 Ощущается как: <b>{weather_data['feels_like']}°C</b>
📝 {weather_data['description']}

💧 Влажность: {weather_data['humidity']}%
📊 Давление: {weather_data['pressure']} мм рт.ст.
💨 Ветер: {weather_data['wind_speed']} м/с
🌀 Порывы ветра: {weather_data['wind_gust']} м/с
"""


# Функции для работы с рассылкой
async def setup_schedule(update: Update, hour: int, minute: int, city: str):
    """Настройка рассылки через кнопку"""
    # Сохраняем настройки в user_data
    update.message.from_user
    schedule_key = f"schedule_{update.message.from_user.id}"

    update.message.chat.bot_data[schedule_key] = {
        'hour': hour,
        'minute': minute,
        'city': city,
        'chat_id': update.message.chat_id,
        'user_name': update.message.from_user.first_name
    }

    # Настраиваем задачу в планировщике
    scheduler = update.message.chat.bot.bot_data.get('scheduler')
    if scheduler:
        # Удаляем старую задачу если есть
        job_id = f'weather_schedule_{update.message.chat_id}'
        try:
            scheduler.remove_job(job_id)
        except:
            pass

        # Добавляем новую задачу
        scheduler.add_job(
            send_scheduled_weather,
            CronTrigger(hour=hour, minute=minute),
            args=[update.message.chat.bot, schedule_key],
            id=job_id,
            name=f"Рассылка для {update.message.from_user.first_name}"
        )

    city_display = "оба города" if city == "Оба" else f"город {city}"
    await update.message.reply_text(
        f"✅ Ежедневная рассылка настроена!\n\n"
        f"⏰ Время: {hour:02d}:{minute:02d}\n"
        f"📍 {city_display.capitalize()}\n\n"
        f"Погода будет приходить автоматически каждый день.",
        reply_markup=get_main_keyboard()
    )


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Текстовая команда для настройки рассылки"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /schedule <час> <минута> [город]\n"
            "Примеры:\n"
            "/schedule 8 0 Севастополь\n"
            "/schedule 9 30 Симферополь\n"
            "/schedule 12 0 Оба\n\n"
            "Или используйте кнопки в меню 'Настроить рассылку'",
            reply_markup=get_main_keyboard()
        )
        return

    try:
        hour = int(context.args[0])
        minute = int(context.args[1])
        city = context.args[2].capitalize() if len(context.args) > 2 else "Оба"

        if city not in ["Севастополь", "Симферополь", "Оба"]:
            await update.message.reply_text(
                "Доступные города: Севастополь, Симферополь или Оба",
                reply_markup=get_main_keyboard()
            )
            return

        await setup_schedule(update, hour, minute, city)

    except ValueError:
        await update.message.reply_text(
            "Пожалуйста, укажите корректное время (числа)",
            reply_markup=get_main_keyboard()
        )


async def stop_schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Остановка рассылки"""
    scheduler = update.message.chat.bot.bot_data.get('scheduler')
    if scheduler:
        job_id = f'weather_schedule_{update.message.chat_id}'
        try:
            scheduler.remove_job(job_id)
        except:
            pass

    # Удаляем настройки
    schedule_key = f"schedule_{update.message.from_user.id}"
    if schedule_key in update.message.chat.bot.bot_data:
        del update.message.chat.bot.bot_data[schedule_key]

    await update.message.reply_text(
        "✅ Рассылка остановлена",
        reply_markup=get_main_keyboard()
    )


async def send_scheduled_weather(bot, schedule_key: str):
    """Отправка погоды по расписанию"""
    schedule_data = bot.bot_data.get(schedule_key)
    if not schedule_data:
        return

    city = schedule_data['city']
    chat_id = schedule_data['chat_id']

    if city == "Оба":
        cities_to_send = ["Севастополь", "Симферополь"]
    else:
        cities_to_send = [city]

    for city_name in cities_to_send:
        weather_data = weather_service.get_current_weather(city_name)
        if weather_data:
            message = format_weather_message(weather_data)
            await bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML')


# Команда для отправки в группу
async def send_to_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка погоды в группу (для админов)"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /send_to_group <id_группы> <город>\n"
            "Пример: /send_to_group -100123456789 Севастополь\n\n"
            "ID группы обычно начинается с -100",
            reply_markup=get_main_keyboard()
        )
        return

    group_id = context.args[0]
    city_name = context.args[1].capitalize()

    if city_name not in CITIES:
        await update.message.reply_text(
            "Доступные города: Севастополь, Симферополь",
            reply_markup=get_main_keyboard()
        )
        return

    await update.message.reply_chat_action(action="typing")

    weather_data = weather_service.get_current_weather(city_name)

    if weather_data:
        message = format_weather_message(weather_data)
        await context.bot.send_message(chat_id=group_id, text=message, parse_mode='HTML')
        await update.message.reply_text(
            f"✅ Погода отправлена в группу {group_id}",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "Не удалось получить данные о погоде",
            reply_markup=get_main_keyboard()
        )


# Главная функция
def main():
    """Запуск бота"""
    if not TELEGRAM_TOKEN or not OPENWEATHER_API_KEY:
        print("Ошибка: Укажите TELEGRAM_TOKEN и OPENWEATHER_API_KEY в файле .env")
        return

    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Инициализация планировщика
    scheduler = AsyncIOScheduler()
    scheduler.start()
    application.bot_data['scheduler'] = scheduler

    # Добавление обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", handle_message))
    application.add_handler(CommandHandler("forecast", handle_message))
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("stop_schedule", stop_schedule_command))
    application.add_handler(CommandHandler("send_to_group", send_to_group_command))

    # Обработчик текстовых сообщений (кнопок)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота
    print("🌤️ Бот погоды запущен...")
    print("Используйте кнопки для навигации")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()