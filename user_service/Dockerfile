FROM python:3.12

WORKDIR /app

COPY ./monitoring_python ./monitoring_python
COPY ./user_service ./user_service
RUN pip install --no-cache-dir -r user_service/requirements.txt

ENV PYTHONPATH=/app

CMD ["uvicorn", "user_service.app.setup.app:app", "--host", "0.0.0.0", "--port", "8000"]
