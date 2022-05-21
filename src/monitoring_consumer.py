import logging
from typing import Dict, List
from kafka import KafkaConsumer
from config import get_kafka_connection_details, get_pg_connection
from json import loads
import time
from psycopg2._psycopg import connection
from sql_queries import run_sql_query

logger = logging.getLogger(__name__)


def insert_monitoring_metrics(conn: connection, metrics: List[Dict]) -> bool:
    """
    Inserts the monitoring metrics into the database. Returns True when there were no metrics or they were inserted
    successfully
    """
    if not metrics:
        return True
    batch_query = ""
    for metric in metrics:
        if metric['regexp'] is None:
            regexp_filter = "NULL"
        else:
            regexp_filter = str(metric['regexp'])

        batch_query += f"INSERT INTO website_availability.availability_monitor_metrics (amm_unix_timestamp, " \
                       f"amd_response_code, amd_response_time, amm_regexp_found) " \
                       f"VALUES ({metric['unix_timestamp']}, {metric['returned_code']}, {metric['response_time']}," \
                       f" {regexp_filter});"

    run_sql_query(conn, batch_query)
    return True


def consumer_main_loop(conn: connection, consumer: KafkaConsumer, retry_sleep_seconds: int = 60) -> bool:
    """
    Consumer main loop. Returns True if messages were consumed, False otherwise
    """
    messages = [m.value for m in consumer]
    if not messages:
        return False
    retries = 0
    successful_commit = False
    while retries < 10 and not successful_commit:
        retries += 1
        messages_written = False
        try:
            messages_written = insert_monitoring_metrics(conn, messages)
            consumer.commit()
            successful_commit = True
        except Exception as e:
            if messages_written:
                error_message = f"Unexpected error trying to commit: {repr(e)}"
            else:
                error_message = f"Unexpected error inserting monitoring metrics: {repr(e)}"
            logging.error(error_message)
            time.sleep(retry_sleep_seconds)
    if retries > 9:
        error_msg = "There is a persisting problem preventing the monitoring consumer from writing messages to" \
                    " the DB. Please check the error logs for more details."
        logging.error(error_msg)
        # This should be sent also to our alerting system so we are warned about a situation that should not happen.
        raise RuntimeError(error_msg)
    return True


def monitoring_consumer(config_path: str, run_once: bool = False) -> None:
    """
    Main call to start the monitoring consumer
    run_once: Used for testing, run the main loop just once.
    """
    details = get_kafka_connection_details(config_path)
    conn = get_pg_connection(config_path)

    consumer = KafkaConsumer(bootstrap_servers=details.service_uri,
                             auto_offset_reset='earliest',
                             security_protocol="SSL",
                             ssl_cafile=details.ca_path,
                             ssl_certfile=details.access_cert_path,
                             ssl_keyfile=details.access_key_path,
                             consumer_timeout_ms=1000,
                             value_deserializer=lambda x: loads(
                                 x.decode('utf-8')),
                             group_id="website_monitoring_consumer",
                             fetch_max_wait_ms=5000,
                             enable_auto_commit=False)

    consumer.subscribe([details.topic_name])

    messages_received = False
    running = True
    while running:
        try:
            messages_received = consumer_main_loop(conn, consumer)
            time.sleep(5)
        except RuntimeError:
            consumer.close()
            conn.close()
            exit(1)
        except Exception as e:
            logger.error(f"Unexpected error found when running the monitoring_consumer: {repr(e)}")
            consumer.close()
            conn.close()
            exit(1)
        if run_once and messages_received:
            running = False
            consumer.close()
            conn.close()
