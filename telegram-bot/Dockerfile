# Используем официальный Python образ
FROM python:3.11-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Копируем файл с ботом
COPY bot.py .

# Копируем requirements.txt (создадим ниже)
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Команда запуска бота
CMD ["python", "bot.py"]