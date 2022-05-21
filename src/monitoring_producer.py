import logging
import re
import time
from dataclasses import dataclass
from json import dumps

import requests
from dataclasses_json import dataclass_json
from kafka import KafkaProducer
from kafka.errors import KafkaTimeoutError

from config import MonitoringProducerConfig, MonitoringWebsiteDetails, get_producer_config

logger = logging.getLogger(__name__)


@dataclass_json
@dataclass
class WebsiteAvailability:
    """Stores website availability metrics"""
    unix_timestamp: int
    returned_code: int
    response_time: float
    regexp: bool


def check_website_availability(monitoring_details: MonitoringWebsiteDetails, timeout) -> WebsiteAvailability:
    """
    Check wether or not a site is available and return metrics
    """

    time_requested = int(time.time())

    response = requests.post(monitoring_details.url, timeout=timeout)

    regexp_found = None
    if monitoring_details.regexp is not None:
        regexp_found = bool(re.findall(
            monitoring_details.regexp, response.text))

    return WebsiteAvailability(time_requested, response.status_code, response.elapsed.microseconds, regexp_found)


def check_website_availability_for_producer(monitoring_details: MonitoringWebsiteDetails, timeout: int):
    """
    Protect the producer from getting the errors derived from an invalid configuration or website checks.
    This will prevent that one failing check disables the rest from being checked.
    Logs are written with every error detected
    """
    try:
        return check_website_availability(monitoring_details, timeout).to_dict()
    except Exception as e:
        logging.error(
            f"Failed to check url, please review its configuration. Url: {monitoring_details.url} "
            f"Id: {monitoring_details.id} Regexp: {monitoring_details.regexp} Error message: {repr(e)}")


def producer_main_loop(run_once: bool, producer_config: MonitoringProducerConfig, producer: KafkaProducer) -> None:
    """
    Producer main loop
    """
    running = True
    app_config = producer_config.monitoring_config
    while running:
        try:
            for monitoring_details in producer_config.monitoring_websites:
                producer.send(producer_config.kafka_details.topic_name,
                              check_website_availability_for_producer(monitoring_details, app_config.timeout))
        except Exception as e:
            # Only kafka-related exceptions should happen here.
            hint = ""
            if type(e) == type(KafkaTimeoutError()):
                hint = "Does the necessary topic exist?"
            logger.error(
                f'Shutting down producer: Sending messages failed after 10 retries with error: {repr(e)}. {hint}')
            # This should be sent also to our alerting system so we are warned about a situation that should not happen.
            producer.close()
            exit(1)
        if running and not run_once:
            time.sleep(app_config.check_periodicity)
        else:
            running = False
            producer.flush()


def monitoring_producer(config_path: str, id: int, run_once: bool = False) -> None:
    """
    Main call to start the monitoring producer
    id: Id based upon which the producer will decide which websites to monitor. See readme for more information.
    run_once: Used for testing, run the main loop just once.
    """

    producer_config = get_producer_config(config_path, id)
    kafka_config = producer_config.kafka_details

    producer = KafkaProducer(
        bootstrap_servers=kafka_config.service_uri,
        security_protocol="SSL",
        ssl_cafile=kafka_config.ca_path,
        ssl_certfile=kafka_config.access_cert_path,
        ssl_keyfile=kafka_config.access_key_path,
        value_serializer=lambda x: dumps(x).encode('utf-8'),
        retries=10
    )

    producer_main_loop(run_once, producer_config, producer)
