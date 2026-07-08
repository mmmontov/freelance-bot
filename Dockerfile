FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py main.py ./
COPY storage/ storage/
COPY exchanges/ exchanges/
COPY watcher/ watcher/
COPY bot/ bot/

CMD ["python", "main.py"]
