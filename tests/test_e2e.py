import time
import pytest
from src.monitoring_consumer import monitoring_consumer
from src.monitoring_producer import monitoring_producer
from src.sql_queries import configure_monitoring_database, run_sql_query
from src.config import get_pg_connection

IT_CONFIG_PATH = "./resources/config_it.yaml"


@pytest.mark.end_to_end
def test_full_solution():
    """
    End to end test:
    * Database schema and required tables are created from scratch
    * The configuration holds 2 websites with wrong configurations and 2 with proper ones
    * The index used in the consumer implies only the first 3 must be used, with only one of them being valid
    * A message must be written into the kafka topic for that valid website check
    * The consumer does not exit on failure of wrong configurations 
        * Wrong configurations are checked and filtered out; It should not be possible to have wrong configurations on runtime
    * This message is consumed by the consumer and written into the PostgreSQL database
    """

    conn = get_pg_connection(IT_CONFIG_PATH)
    run_sql_query(conn, "DROP SCHEMA IF EXISTS website_availability CASCADE")
    configure_monitoring_database(conn)
    run_sql_query(conn,
                  "INSERT INTO website_availability.availability_monitor_config (amc_url_with_schema, amc_regexp) "
                  "VALUES('http://www.example.com', '*')")
    run_sql_query(conn,
                  "INSERT INTO website_availability.availability_monitor_config (amc_url_with_schema, amc_regexp) "
                  "VALUES('http:///www.example.com', '.*')")
    run_sql_query(conn,
                  "INSERT INTO website_availability.availability_monitor_config (amc_url_with_schema, amc_regexp) "
                  "VALUES('http://www.example.com', '.*')")
    run_sql_query(conn,
                  "INSERT INTO website_availability.availability_monitor_config (amc_url_with_schema, amc_regexp) "
                  "VALUES('http://www.example.com', '.*')")

    monitoring_producer(IT_CONFIG_PATH, 1, run_once=True)
    monitoring_consumer(IT_CONFIG_PATH, run_once=True)

    expected_new_data = run_sql_query(conn,
                                      "SELECT * FROM website_availability.availability_monitor_metrics",
                                      fetch_results=True)
    conn.close()
    assert (len(expected_new_data) == 1)
