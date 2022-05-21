import pytest

from src.sql_queries import run_sql_query, configure_monitoring_database, CREATE_SCHEMA, CREATE_AMC
import testing.postgresql
import psycopg2


@pytest.mark.integration_test
def test_run_sql_query():
    """
    Create a table and test that the table is empty. If creation failed, the table query would fail too.
    """
    with testing.postgresql.Postgresql() as postgresql:
        conn = psycopg2.connect(**postgresql.dsn())
        run_sql_query(conn, CREATE_SCHEMA)
        run_sql_query(conn, CREATE_AMC)
        results = run_sql_query(
            conn, "SELECT * FROM website_availability.availability_monitor_config", fetch_results=True)
        conn.close()
    assert (results == [])


@pytest.mark.integration_test
def test_run_sql_query_massive_amount_of_queries():
    """
    There is no exception thrown when a massive query is submitted.
    """
    with testing.postgresql.Postgresql() as postgresql:
        conn = psycopg2.connect(**postgresql.dsn())
        run_sql_query(conn, CREATE_SCHEMA)
        run_sql_query(
            conn, CREATE_SCHEMA * 2000000)
        conn.close()


@pytest.mark.integration_test
def test_configure_monitoring_database():
    """
    Confirm the tables created when configuring the database exist.
    """
    with testing.postgresql.Postgresql() as postgresql:
        conn = psycopg2.connect(**postgresql.dsn())
        configure_monitoring_database(conn)
        config = run_sql_query(conn,
                               "SELECT * FROM website_availability.availability_monitor_config", fetch_results=True)
        metrics = run_sql_query(conn,
                                "SELECT * FROM website_availability.availability_monitor_metrics", fetch_results=True)
        conn.close()
    assert (metrics == config == [])
