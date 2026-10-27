FROM python:3.12-slim

WORKDIR /app

# Avval kutubxonalarni o'rnatib olamiz
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Barcha loyiha fayllarini serverga nusxalaymiz
COPY . .

# Botni avtomatik ishga tushiramiz
CMD ["python", "main.py"]