import configparser
import json
import logging.config
import re
from datetime import datetime
from time import sleep

import paho.mqtt.client as mqtt
import requests

logging.config.fileConfig("persistent_data/config/logging.conf")
logger = logging.getLogger(__name__)

app_config = configparser.ConfigParser()
app_config.read("persistent_data/config/app.conf")


class BaseClass(object):
    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)


class IdalgoClient(BaseClass):
    def __init__(self):
        super().__init__()
        self._session = requests.Session()
        self._config = configparser.ConfigParser()
        self.read_config()
        return

    def read_config(self, file='persistent_data/config/idalgo_client.conf'):
        try:
            self._config.read(file)
            self.log.info('Configuration file read')
        except Exception as e:
            self.log.exception(e)
            raise e

    def login(self):
        try:
            connection = self._config['connection']
            user = connection['user']
            data = {'user': user, 'password': connection['password'], 'place': 'bill', 'submit': 'ВОЙТИ+'}
            response = self._session.post("https://lk.idalgo.pro/auth", data=data)
            if response.text == '' and response.status_code == 200:
                self.log.info(f'Logged in as {user}')
            else:
                raise ConnectionError(f'User {user} login failed')
        except Exception as e:
            self.log.exception(e)
            raise e

    def logout(self):
        try:
            self._session.get("https://lk.idalgo.pro/auth?id=logout")
            self.log.info('Logged out')
        except Exception as e:
            self.log.exception(e)
            raise e

    def _get_main_page(self) -> str:
        try:
            response = self._session.get('https://lk.idalgo.pro/main')
            self.log.info('Main page downloaded')
            return response.text
        except Exception as e:
            self.log.exception(e)
            raise e

    def get_balance(self) -> float:
        page = self._get_main_page()
        page = re.sub(r"\s+", "", page, flags=re.UNICODE)
        try:
            balance = float(re.findall(r"Баланс:<b>(.*?)</b>", page)[0])
            self.log.info('Current account balance received')
            return balance
        except Exception as e:
            self.log.exception(e)
            raise e


class MQTTClient(BaseClass):
    def __init__(self):
        super().__init__()
        self._client = mqtt.Client()
        self._config = configparser.ConfigParser()
        self.read_config()
        return

    def read_config(self, file='persistent_data/config/mqtt_client.conf'):
        try:
            self._config.read(file)
            self.log.info('Configuration file read')
        except Exception as e:
            self.log.exception(e)
            raise e

    def connect(self):
        try:
            connection = self._config['connection']
            self._client.connect(connection['host'])
            self.log.info('Client connected to mqtt server')
        except Exception as e:
            self.log.exception(e)
            raise e

    def publish_config(self):
        try:
            data = {"device_class": "monetary",
                    "name": "IdalgoBalance",
                    "unique_id": "IdalgoBalanceProvider",
                    "state_topic": "homeassistant/sensor/IdalgoBalanceProvider/state",
                    "unit_of_measurement": "₽"}
            data = json.dumps(data)
            self._client.publish("homeassistant/sensor/IdalgoBalanceProvider/config", data)
            self.log.info('Sensor configuration published')
        except Exception as e:
            self.log.exception(e)
            raise e

    def publish_config_reset(self):
        try:
            self._client.publish("homeassistant/sensor/IdalgoBalanceProvider/config", "")
            self.log.info('Sensor configuration reset command published')
        except Exception as e:
            self.log.exception(e)
            raise e

    def publish_balance(self, balance):
        try:
            self._client.publish("homeassistant/sensor/IdalgoBalanceProvider/state", balance)
            self.log.info('Current account balance published')
        except Exception as e:
            self.log.exception(e)
            raise e

    def publish_system_state(self, started_utc: str, error_count: int, last_error: Exception or None):
        try:
            if last_error is not None:
                last_error = repr(last_error)[:75]
            data = {'error_count': error_count,
                    'last_error': last_error,
                    'started_utc': started_utc,
                    'updated_utc': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')}
            data = json.dumps(data)
            self._client.publish("homeassistant/sensor/IdalgoBalanceProvider/system", data)
        except Exception as e:
            self.log.exception(e)


if __name__ == '__main__':
    logger.info('Application started')
    idalgo = IdalgoClient()
    mqtt = MQTTClient()

    server_started = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
    error_count = 0
    current_balance = 0

    mqtt.connect()
    mqtt.publish_system_state(server_started, error_count, None)
    mqtt.publish_config()

    while True:
        try:
            idalgo.login()
            balance = idalgo.get_balance()
            idalgo.logout()

            if balance != current_balance:
                mqtt.connect()
                mqtt.publish_balance(balance)
                current_balance = balance

        except Exception as e:
            error_count += 1
            mqtt.connect()
            mqtt.publish_system_state(server_started, error_count, e)

        finally:
            timeout_min = int(app_config['settings']['timeout'])
            sleep(timeout_min * 60)
