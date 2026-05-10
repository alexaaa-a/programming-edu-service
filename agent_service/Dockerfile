FROM python:3.12

WORKDIR /app
COPY ./monitoring_python ./monitoring_python
COPY ./agent_service ./agent_service
RUN pip install --no-cache-dir -r agent_service/requirements.txt

ENV PYTHONPATH=/app

CMD ["uvicorn", "agent_service.app.setup.main:app", "--host", "0.0.0.0", "--port", "8000"]
