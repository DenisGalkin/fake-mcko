FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates
COPY static ./static

RUN mkdir -p /app/data/user_answers

EXPOSE 4000

CMD ["gunicorn", "--bind", "0.0.0.0:4000", "--workers", "2", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
