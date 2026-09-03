FROM python:3.11-slim

WORKDIR /app

COPY data/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common ./common
COPY data/create_db.py data/source_data.csv ./

ENV PYTHONPATH=/app
ENV CSV_PATH=/app/source_data.csv

CMD ["python", "create_db.py"]
