FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY create_db.py source_data.csv ./

ENV CSV_PATH=/app/source_data.csv

CMD ["python", "create_db.py"]
