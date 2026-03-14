FROM python:3.12

WORKDIR /app

COPY . ./task_service
RUN pip install --no-cache-dir -r task_service/requirements.txt

ENV PYTHONPATH=/app