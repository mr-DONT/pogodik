import logging
import requests
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ваши API ключи прямо в коде
TELEGRAM_TOKEN = "8358614012:AAESe4HkCPyrBKR8So9g-lFCRIPf-H4lCV8"
OPENWEATHER_API_KEY = "9ea9ea45adc20853a3f4f8b397aed3f9"

# Координаты городов
CITIES = {
    'Севастополь': {'lat': 44.6167, 'lon': 33.5254},
    'Симферополь': {'lat': 44.9572, 'lon': 34.1108}
}

# Клавиатуры
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🌤️ Севастополь"), KeyboardButton("🌤️ Симферополь")],
        [KeyboardButton("📅 Прогноз на день")],
        [KeyboardButton("⚙️ Настроить рассылку"), KeyboardButton("🆘 Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_forecast_keyboard():
    keyboard = [
        [KeyboardButton("📅 Севастополь прогноз"), KeyboardButton("📅 Симферополь прогноз")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_schedule_keyboard():
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
    
    def get_current_weather(self, city_name: str):
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
            
        except Exception as e:
            logger.error(f"Ошибка получения погоды: {e}")
            return None
    
    def get_daily_forecast(self, city_name: str):
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
                'cnt': 8
            }
            
            response = requests.get(self.forecast_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            return self._format_forecast_data(data, city_name)
            
        except Exception as e:
            logger.error(f"Ошибка получения прогноза: {e}")
            return None
    
    def _format_weather_data(self, data, city_name):
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
            'timestamp': datetime.fromtimestamp(data['dt'])
        }
    
    def _format_forecast_data(self, data, city_name):
        forecast_text = f"📅 Прогноз погоды в {city_name} на 24 часа:\n\n"
        
        for item in data['list'][::2]:
            time_str = datetime.fromtimestamp(item['dt']).strftime('%H:%M')
            temp = round(item['main']['temp'])
            desc = item['weather'][0]['description'].capitalize()
            forecast_text += f"🕐 {time_str}: {temp}°C, {desc}\n"
        
        return forecast_text

# Создаем сервис погоды
weather_service = WeatherService(OPENWEATHER_API_KEY)

# Хранение расписаний
schedules = {}

# Обработчики
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌤️ Бот погоды для Севастополя и Симферополя!\n"
        "Выберите действие:",
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📋 Как пользоваться ботом:

1. Текущая погода:
   Нажмите кнопку с названием города

2. Прогноз на день:
   Нажмите "📅 Прогноз на день"
   Выберите город

3. Ежедневная рассылка:
   Нажмите "⚙️ Настроить рассылку"
   Выберите время и город

4. Команды:
   /start - Главное меню
   /weather <город> - Погода
   /forecast <город> - Прогноз
   /send_to_group <id группы> <город> - Отправить в группу
   /help - Эта справка
    """
    await update.message.reply_text(help_text, reply_markup=get_main_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Текущая погода
    if text == "🌤️ Севастополь":
        await send_weather(update, "Севастополь")
    elif text == "🌤️ Симферополь":
        await send_weather(update, "Симферополь")
    
    # Меню прогноза
    elif text == "📅 Прогноз на день":
        await update.message.reply_text("Выберите город для прогноза:", reply_markup=get_forecast_keyboard())
    elif text == "📅 Севастополь прогноз":
        await send_forecast(update, "Севастополь")
    elif text == "📅 Симферополь прогноз":
        await send_forecast(update, "Симферополь")
    
    # Меню рассылки
    elif text == "⚙️ Настроить рассылку":
        await update.message.reply_text("Настройте ежедневную рассылку:", reply_markup=get_schedule_keyboard())
    elif text == "⏰ Севастополь в 8:00":
        await setup_schedule(update, 8, 0, "Севастополь")
    elif text == "⏰ Симферополь в 8:00":
        await setup_schedule(update, 8, 0, "Симферополь")
    elif text == "⏰ Оба города в 9:00":
        await setup_schedule(update, 9, 0, "Оба")
    elif text == "⏰ Оба города в 12:00":
        await setup_schedule(update, 12, 0, "Оба")
    elif text == "❌ Остановить рассылку":
        await stop_schedule(update)
    
    # Навигация
    elif text == "⬅️ Назад":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard())
    elif text == "🆘 Помощь":
        await help_command(update, context)
    
    # Текстовые команды
    elif text.startswith("/weather "):
        city = text.replace("/weather ", "").strip()
        await send_weather(update, city)
    elif text.startswith("/forecast "):
        city = text.replace("/forecast ", "").strip()
        await send_forecast(update, city)
    
    else:
        await update.message.reply_text("Используйте кнопки для навигации", reply_markup=get_main_keyboard())

async def send_weather(update: Update, city_name: str):
    city_name = city_name.replace("🌤️ ", "").strip().capitalize()
    
    if city_name not in CITIES:
        await update.message.reply_text("Доступные города: Севастополь, Симферополь", reply_markup=get_main_keyboard())
        return
    
    weather_data = weather_service.get_current_weather(city_name)
    
    if weather_data:
        message = f"""
🌤️ Погода в {weather_data['city']}
📅 {weather_data['timestamp'].strftime('%d.%m.%Y %H:%M')}

🌡️ Температура: {weather_data['temperature']}°C
🤔 Ощущается как: {weather_data['feels_like']}°C
📝 {weather_data['description']}

💧 Влажность: {weather_data['humidity']}%
📊 Давление: {weather_data['pressure']} мм рт.ст.
💨 Ветер: {weather_data['wind_speed']} м/с
🌀 Порывы: {weather_data['wind_gust']} м/с
        """
        await update.message.reply_text(message, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("Ошибка получения данных", reply_markup=get_main_keyboard())

async def send_forecast(update: Update, city_name: str):
    city_name = city_name.replace("📅 ", "").replace(" прогноз", "").strip().capitalize()
    
    if city_name not in CITIES:
        await update.message.reply_text("Доступные города: Севастополь, Симферополь", reply_markup=get_forecast_keyboard())
        return
    
    forecast = weather_service.get_daily_forecast(city_name)
    
    if forecast:
        await update.message.reply_text(forecast, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("Ошибка получения прогноза", reply_markup=get_main_keyboard())

# Функции рассылки
async def setup_schedule(update: Update, hour: int, minute: int, city: str):
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name
    
    # Сохраняем расписание
    schedules[chat_id] = {
        'hour': hour,
        'minute': minute,
        'city': city,
        'user_name': user_name
    }
    
    # Настраиваем задачу
    scheduler = AsyncIOScheduler()
    
    # Удаляем старую задачу если есть
    job_id = f"weather_{chat_id}"
    try:
        scheduler.remove_job(job_id)
    except:
        pass
    
    # Добавляем новую задачу
    scheduler.add_job(
        send_scheduled_weather,
        CronTrigger(hour=hour, minute=minute),
        args=[update.application, chat_id, city],
        id=job_id
    )
    
    scheduler.start()
    
    city_display = "оба города" if city == "Оба" else city
    await update.message.reply_text(
        f"✅ Рассылка настроена!\n"
        f"⏰ Время: {hour:02d}:{minute:02d}\n"
        f"📍 {city_display}\n\n"
        f"Погода будет приходить автоматически каждый день.",
        reply_markup=get_main_keyboard()
    )

async def stop_schedule(update: Update):
    chat_id = update.message.chat_id
    
    if chat_id in schedules:
        del schedules[chat_id]
    
    await update.message.reply_text("✅ Рассылка остановлена", reply_markup=get_main_keyboard())

async def send_scheduled_weather(app, chat_id: int, city: str):
    if city == "Оба":
        cities = ["Севастополь", "Симферополь"]
    else:
        cities = [city]
    
    for city_name in cities:
        weather_data = weather_service.get_current_weather(city_name)
        if weather_data:
            message = f"⏰ Ежедневная рассылка погоды:\n\n" + \
                     f"🌤️ Погода в {weather_data['city']}\n" + \
                     f"🌡️ Температура: {weather_data['temperature']}°C\n" + \
                     f"📝 {weather_data['description']}\n" + \
                     f"💧 Влажность: {weather_data['humidity']}%"
            
            await app.bot.send_message(chat_id=chat_id, text=message)

# Команда отправки в группу
async def send_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /send_to_group <id_группы> <город>\n"
            "Пример: /send_to_group -100123456789 Севастополь"
        )
        return
    
    group_id = context.args[0]
    city_name = context.args[1].capitalize()
    
    if city_name not in CITIES:
        await update.message.reply_text("Доступные города: Севастополь, Симферополь")
        return
    
    weather_data = weather_service.get_current_weather(city_name)
    
    if weather_data:
        message = f"""
🌤️ Погода в {weather_data['city']}
📅 {weather_data['timestamp'].strftime('%d.%m.%Y %H:%M')}

🌡️ Температура: {weather_data['temperature']}°C
🤔 Ощущается как: {weather_data['feels_like']}°C
📝 {weather_data['description']}

💧 Влажность: {weather_data['humidity']}%
📊 Давление: {weather_data['pressure']} мм рт.ст.
💨 Ветер: {weather_data['wind_speed']} м/с
        """
        await context.bot.send_message(chat_id=group_id, text=message)
        await update.message.reply_text(f"✅ Погода отправлена в группу {group_id}")
    else:
        await update.message.reply_text("Ошибка получения данных")

# Главная функция
def main():
    print("🚀 Запуск бота погоды...")
    print(f"Токен: {TELEGRAM_TOKEN[:15]}...")
    print(f"API ключ: {OPENWEATHER_API_KEY[:15]}...")
    
    try:
        # Создаем приложение
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Добавляем обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("send_to_group", send_to_group))
        app.add_handler(CommandHandler("weather", handle_message))
        app.add_handler(CommandHandler("forecast", handle_message))
        
        # Обработчик текстовых сообщений
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Запускаем бота
        print("✅ Бот запущен. Ожидание сообщений...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    main()
