FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Папка для хранения repos.json и versions.json (монтируется как volume)
VOLUME ["/app/data"]

CMD ["python", "-u", "bot.py"]
