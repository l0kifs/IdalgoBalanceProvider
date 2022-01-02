FROM python:3.8-slim-buster

LABEL name="IdalgoBalanceProvider"
LABEL version="1.0"
LABEL description="The application provide current account balance for specified account of Idalgo internet provider"

WORKDIR /app

COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

ADD application application
ADD persistent_data persistent_data

CMD [ "python3" , "application/main.py" ]