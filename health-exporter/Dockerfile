FROM python:3.11-alpine

# Устанавливаем зависимости системы
RUN apk add --no-cache \
    gcc \
    musl-dev \
    && rm -rf /var/cache/apk/*

# Создаем пользователя для безопасности
RUN adduser -D -s /bin/sh healthexporter

# Рабочая директория
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY app.py .

# Меняем владельца
RUN chown -R healthexporter:healthexporter /app

# Переключаемся на пользователя
USER healthexporter

# Открываем порт
EXPOSE 8080

# Команда запуска
CMD ["python", "app.py"]