FROM python:3.12

WORKDIR /app

COPY ./monitoring_python ./monitoring_python
COPY ./api_gateway ./api_gateway
RUN pip install --no-cache-dir -r api_gateway/requirements.txt

ENV PYTHONPATH=/app

CMD ["uvicorn", "api_gateway.app.setup.app:app", "--host", "0.0.0.0", "--port", "8000"]
