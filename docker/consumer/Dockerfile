FROM python:3.9

RUN mkdir /app
WORKDIR /app
ADD . /app/
RUN apt update
RUN apt --assume-yes install python3-dev libpq-dev
RUN pip install -r requirements.txt

CMD ["python", "/app/src/__main__.py", "start-consumer", "/app/config/config.yaml"]
