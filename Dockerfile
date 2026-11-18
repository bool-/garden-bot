# Headless Garden Bot: no Qt, small image. The control API lets the Qt window
# on another machine watch and steer it (python app.py --remote URL).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GAME_DATA_PATH=/state/game_data.json
WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY . .

# Config, cookies, logs and learned state live in the mounted /state dir.
WORKDIR /state
CMD ["python", "/app/app.py", "--headless", "--serve"]
