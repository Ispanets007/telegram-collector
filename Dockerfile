FROM python:3.11-slim

WORKDIR /app

# Встановлюємо залежності окремим шаром для кешування
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Директорія для даних та сесій
RUN mkdir -p data sample_data

# Змінні середовища підтягуються з .env через docker-compose або --env-file
ENV PYTHONUNBUFFERED=1

# За замовчуванням — інкрементний збір
CMD ["python", "scripts/collect.py"]
