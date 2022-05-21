FROM python:3.9

RUN mkdir /app
WORKDIR /app
ADD . /app/
RUN apt install libpython3-dev libpq-dev
RUN pip install -r requirements.txt
RUN cd /app

CMD ["python", "/app/src/__main__.py", "start-producer", "/app/config/config.yaml", "$ID"]
