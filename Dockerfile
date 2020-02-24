FROM python:3.8.0

WORKDIR /usr/src/app
COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends z3
RUN pip install --upgrade pip && pip install -r requirements.txt
