import pytest
from config import KafkaConnectionDetails, MonitoringConfig, MonitoringWebsiteDetails, PgConnectionDetails, \
    base64ToString, get_pg_connection_details, get_kafka_connection_details, get_monitoring_config, sanity_checks_ok
import base64
import logging

TEST_CONFIG_PATH = "./resources/config.yaml"
LOGGER = logging.getLogger(__name__)


def test_base64ToString():
    assert (base64ToString(b'AAAA') == '\x00\x00\x00')


def test_get_monitoring_config():
    cfg = get_monitoring_config(TEST_CONFIG_PATH)
    assert (cfg == MonitoringConfig(1, 10, 60))


def test_get_pg_connection_details(mocker):
    encoded_usr = base64.b64encode(bytes('username-for-test', 'utf-8'))
    encoded_pwd = base64.b64encode(bytes('password-for-test', 'utf-8'))

    mocker.patch('config.get_k8s_secret_data', return_value={
        "username": encoded_usr, "password": encoded_pwd})
    cfg = get_pg_connection_details(TEST_CONFIG_PATH)
    assert (cfg == PgConnectionDetails("fake-pg-host", 21770,
                                       "monitoring", "username-for-test", "password-for-test"))


def test_kafka_connection_details(mocker):
    encoded_ac = base64.b64encode(bytes('ac', 'utf-8'))
    encoded_ak = base64.b64encode(bytes('ak', 'utf-8'))
    encoded_ca = base64.b64encode(bytes('ca', 'utf-8'))

    mocker.patch('config.get_k8s_secret_data', return_value={
        "access_certificate": encoded_ac, "access_key": encoded_ak, "ca_certificate": encoded_ca})
    mocker.patch('config.write_cert', return_value=True)
    config_path = TEST_CONFIG_PATH
    cfg = get_kafka_connection_details(config_path)
    assert (cfg == KafkaConnectionDetails(
        "fake-kafka-host:2222", "./kafka_access_cert", "./kafka_access_key", "./kafka_ca", "website_availability"))


def test_sanity_checks_ok(caplog):
    monitoring_cfg = MonitoringConfig(100, 10, 5)
    urls = []
    with caplog.at_level(logging.WARNING):
        result = sanity_checks_ok(monitoring_cfg, urls)
    assert (not result) and (
            "Producer might not have time to check and send all the requests." in caplog.text)


def test_monitoring_website_details():
    m = MonitoringWebsiteDetails(1, "www.test.com", "nonvalidregexp[")
    assert (not m.is_valid())
