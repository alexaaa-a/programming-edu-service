FROM python:3.12

WORKDIR /app

COPY ./submission_service ./submission_service
RUN pip install --no-cache-dir -r submission_service/requirements.txt

ENV PYTHONPATH=/app