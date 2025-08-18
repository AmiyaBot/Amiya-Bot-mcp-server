FROM python:3.10-slim

WORKDIR /app

RUN mkdir -p /app/resources

RUN apt-get update

RUN apt-get install -y --no-install-recommends \
    git \
    build-essential

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
