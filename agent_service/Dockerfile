FROM python:3.12

WORKDIR /app
COPY ./agent_service ./agent_service
RUN pip install --no-cache-dir -r agent_service/requirements.txt

ENV PYTHONPATH=/app

