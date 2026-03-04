FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Папка для хранения last_version.txt (удобно монтировать как volume)
VOLUME ["/app"]

CMD ["python", "-u", "bot.py"]
