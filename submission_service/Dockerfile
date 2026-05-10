FROM python:3.12

WORKDIR /app

COPY ./monitoring_python ./monitoring_python
COPY ./submission_service ./submission_service
RUN pip install --no-cache-dir -r submission_service/requirements.txt

ENV PYTHONPATH=/app

CMD ["uvicorn", "submission_service.app.setup.app:app", "--host", "0.0.0.0", "--port", "8000"]
