from dataclasses import dataclass
import logging
from typing import Dict, List
import yaml
from kubernetes import client, config
import base64
import os
from psycopg2._psycopg import connection
from psycopg2 import connect
from sql_queries import run_sql_query
import re
import validators

logger = logging.getLogger(__name__)


def base64ToString(b):
    """Transform a base64 encoded data to string"""
    return base64.b64decode(b).decode('utf-8')


def get_app_config(config_path: str) -> Dict:
    """Load the yaml file specified in the config_path"""
    with open(config_path, "r") as config_file:
        cfg = yaml.load(config_file, Loader=yaml.FullLoader)
    return cfg


@dataclass
class MonitoringWebsiteDetails:
    """Store the configuration of one website to monitor"""
    id: int
    url: str
    regexp: str

    def is_valid(self):
        is_valid = True
        if self.regexp:
            try:
                re.compile(self.regexp)
            except re.error:
                is_valid = False
                logger.error(
                    f'Invalid regexp found for website: "{self.url}" with ID: "{self.id}" and regexp: "{self.regexp}". '
                    f'This website will not be monitored!')
        if not (self.url.startswith("http://") or self.url.startswith("https://")):
            is_valid = False
            logger.error(
                f'Url missing schema for url: "{self.url}" with ID: "{self.id}". This website will not be monitored!')
        if not validators.url(self.url):
            is_valid = False
            logger.error(
                f'Invalid url for url: "{self.url}" with ID: "{self.id}". This website will not be monitored!')

        return is_valid


@dataclass
class MonitoringConfig:
    """Store the monitoring app general configuration"""
    websites_per_container: int
    timeout: int
    check_periodicity: int


def get_monitoring_config(config_path: str) -> MonitoringConfig:
    """Extract the monitoring config given the configuration path"""
    monitoring_cfg = get_app_config(config_path).get("monitor")
    return MonitoringConfig(int(monitoring_cfg["websites_per_container"]),
                            int(monitoring_cfg["timeout"]),
                            int(monitoring_cfg["check_periodicity"]))


def write_cert(path: str, content: str) -> None:
    """Decode and write a certificate to the specified path"""
    with open(path, 'w') as f:
        f.write(base64ToString(content))


@dataclass
class KafkaConnectionDetails:
    """Store the kafka connection details"""
    service_uri: str
    access_cert_path: str
    access_key_path: str
    ca_path: str
    topic_name: str


def get_k8s_secret_data(namespace: str, secret_name: str) -> Dict:
    """Extract the information from a kubernetes secret"""
    config.load_config()

    v1 = client.CoreV1Api()
    return v1.read_namespaced_secret(secret_name, namespace).data


def get_kafka_connection_details(config_path) -> KafkaConnectionDetails:
    """Load the kafka connection details from the configuration path and the kubernetes secrets stored in the cluster"""
    kafka_cfg = get_app_config(config_path).get("kafka")
    service_uri = kafka_cfg["service_uri"]
    secret = kafka_cfg["credentials_secret"]
    namespace = kafka_cfg["credentials_namespace"]
    secret_folder = kafka_cfg["secrets_storage_folder"]
    topic_name = kafka_cfg["topic_name"]

    KAFKA_ACCESS_CERT_PATH = os.path.join(secret_folder, "kafka_access_cert")
    KAFKA_ACCESS_KEY_PATH = os.path.join(secret_folder, "kafka_access_key")
    KAFKA_CA_PATH = os.path.join(secret_folder, "kafka_ca")

    secret = get_k8s_secret_data(namespace, secret)

    write_cert(KAFKA_ACCESS_CERT_PATH, secret["access_certificate"])
    write_cert(KAFKA_ACCESS_KEY_PATH, secret["access_key"])
    write_cert(KAFKA_CA_PATH, secret["ca_certificate"])

    return KafkaConnectionDetails(service_uri, KAFKA_ACCESS_CERT_PATH, KAFKA_ACCESS_KEY_PATH, KAFKA_CA_PATH, topic_name)


@dataclass
class PgConnectionDetails:
    """Store PostgreSQL connection details"""
    host: str
    port: int
    database: str
    user: str
    password: str


def get_pg_connection_details(config_path: str) -> PgConnectionDetails:
    """
    Load the PostgreSQL connection details from the configuration file and kubernetes secrets stored in the cluster
    """
    pg_cfg = get_app_config(config_path).get("database")
    host = pg_cfg["host"]
    port = pg_cfg["port"]
    database = pg_cfg["database"]
    secret = pg_cfg["credentials_secret"]
    namespace = pg_cfg["credentials_namespace"]

    secret_data = get_k8s_secret_data(namespace, secret)

    return PgConnectionDetails(host, port, database, base64ToString(secret_data["username"]),
                               base64ToString(secret_data["password"]))


def sanity_checks_ok(app_config: MonitoringConfig, urls_to_monitor: List[MonitoringWebsiteDetails]) -> bool:
    """
    Performs a few checks on the configuration provided. 
    Returns False in case the program should stop.
    Logs warnings in case of potentially conflicting configuration is identified.
    """

    if app_config.check_periodicity < 40:
        logging.warning(
            "Producer might not have time to check and send all the requests.")
    if len(urls_to_monitor) == 0:
        logging.error(
            "No websites to monitor. The ID and websites_per_container provided are bigger than the "
            "number of configured websites.")
        return False
    return True


def get_pg_connection(config_path: str) -> connection:
    """Starts and returns a connection to PostgreSQL"""
    details = get_pg_connection_details(config_path)
    pg_uri = f"postgres://{str(details.user)}:{details.password}@{details.host}:" \
             f"{details.port}/{details.database}?sslmode=require"
    conn = connect(pg_uri)
    conn.autocommit = True
    return conn


@dataclass
class MonitoringProducerConfig:
    """Stores all the required producer configuration"""
    kafka_details: KafkaConnectionDetails
    monitoring_config: MonitoringConfig
    monitoring_websites: List[MonitoringWebsiteDetails]


def get_producer_config(config_path: str, id: int) -> MonitoringProducerConfig:
    """Prepares and returns all the required configuration for the monitoring producer"""
    kafka_config = get_kafka_connection_details(config_path)
    app_config = get_monitoring_config(config_path)
    conn = get_pg_connection(config_path)
    urls_to_monitor = get_monitored_urls(
        conn, id, app_config.websites_per_container)
    conn.close()
    if not sanity_checks_ok(app_config, urls_to_monitor):
        exit(1)
    valid_urls_to_monitor = [url for url in urls_to_monitor if url.is_valid()]
    return MonitoringProducerConfig(kafka_config, app_config, valid_urls_to_monitor)


def get_monitored_urls(conn: connection, id: int, websites_per_container: int) -> List[MonitoringWebsiteDetails]:
    """Extracts from the database the list of websites to monitor and their configuration"""
    sql_query = f'SELECT * from website_availability.availability_monitor_config a WHERE a.amc_id > {id - 1} ' \
                f'AND a.amc_id < {id + websites_per_container}'
    result = run_sql_query(conn, sql_query, fetch_results=True)
    return [MonitoringWebsiteDetails(x[0], x[1], x[2]) for x in result]
