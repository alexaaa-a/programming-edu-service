FROM python:3.12

WORKDIR /app

COPY ./user_service ./user_service
RUN pip install --no-cache-dir -r user_service/requirements.txt

ENV PYTHONPATH=/app