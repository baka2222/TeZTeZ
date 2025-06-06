FROM python:3.11
WORKDIR /app
COPY bot/. .
COPY backend ./backend
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
ENV PYTHONPATH=/app:/app/backend