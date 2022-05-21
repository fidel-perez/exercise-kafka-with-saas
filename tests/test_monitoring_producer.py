import logging
import re
import pytest
from requests.exceptions import InvalidSchema
from src.config import KafkaConnectionDetails, MonitoringConfig, MonitoringProducerConfig, MonitoringWebsiteDetails
from src.monitoring_producer import check_website_availability, check_website_availability_for_producer, \
    producer_main_loop
from kafka.errors import KafkaTimeoutError

LOGGER = logging.getLogger(__name__)


class MockResponse:
    def __init__(self, status_code, text, elapsed_microseconds):
        self.status_code = status_code
        self.text = text
        self.elapsed = lambda: None
        self.elapsed.microseconds = elapsed_microseconds

    def json(self):
        return self.json_data


class MockedProducer(object):
    def __init__(self, failing=False) -> None:
        self.failing = failing
        pass

    def send(self):
        if self.failing:
            raise KafkaTimeoutError

    def close(self):
        pass

    def flush(self):
        pass


def test_check_website_availability_happy_path(mocker):
    monitoring_details = MonitoringWebsiteDetails(
        1, "http://www.website.com", ".*")

    mocked_response = MockResponse(
        200, text="this is text", elapsed_microseconds=1)

    mocker.patch(
        'src.monitoring_producer.requests.post', return_value=mocked_response)
    availability = check_website_availability(monitoring_details, 20)
    assert (availability.returned_code == 200)
    assert (availability.regexp == True)


def test_check_website_availability_wrong_schema(mocker):
    def raise_invalid_schema(*args, timeout):
        raise InvalidSchema

    monitoring_details = MonitoringWebsiteDetails(
        1, "www.website.com", None)

    mocker.patch(
        'src.monitoring_producer.requests.post', side_effect=raise_invalid_schema)

    with pytest.raises(InvalidSchema):
        check_website_availability(monitoring_details, 20)


def test_check_website_availability_wrong_regexp(mocker):
    monitoring_details = MonitoringWebsiteDetails(
        1, "http://www.website.com", "*")

    mocked_response = MockResponse(
        200, text="this is text", elapsed_microseconds=1)

    mocker.patch(
        'src.monitoring_producer.requests.post', return_value=mocked_response)
    with pytest.raises(re.error):
        check_website_availability(monitoring_details, 20)


def test_check_website_availability_for_producer_exception(mocker, caplog):
    mocker.patch(
        'src.monitoring_producer.check_website_availability', return_value=True)

    monitoring_details = MonitoringWebsiteDetails(1, "www.website.com", None)
    with caplog.at_level(logging.WARNING):
        check_website_availability_for_producer(monitoring_details, 1)
    assert (
            "Failed to check url, please review its configuration. Url: www.website.com Id: 1 Regexp: None"
            in caplog.text)


def test_producer_main_loop_exception(mocker):
    mocked_producer = MockedProducer(failing=True)
    kafka_details = KafkaConnectionDetails(
        "fake-kafka-host:2222", "./kafka_access_cert", "./kafka_access_key", "./kafka_ca", "website_availability")
    m = MonitoringWebsiteDetails(1, "www.test.com", ".*")
    cfg = MonitoringConfig(1, 10, 60)
    producer_config = MonitoringProducerConfig(kafka_details, cfg, m)
    with pytest.raises(SystemExit):
        producer_main_loop(True, producer_config, mocked_producer)
