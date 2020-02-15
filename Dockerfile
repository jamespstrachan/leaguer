FROM python:3.8.0

WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt
