FROM python:3.12

WORKDIR /app

COPY . ./task_service
RUN pip install --no-cache-dir -r task_service/requirements.txt

ENV PYTHONPATH=/app

CMD ["uvicorn", "task_service.app.setup.app:app", "--host", "0.0.0.0", "--port", "8000"]