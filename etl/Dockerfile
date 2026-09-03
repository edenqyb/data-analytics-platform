FROM python:3.11-slim

WORKDIR /app

COPY etl/requirements.txt .
RUN pip install -r requirements.txt

COPY common ./common
COPY etl/etl.py .

ENV PYTHONPATH=/app

CMD ["python", "etl.py"]
