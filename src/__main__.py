from posixpath import abspath, dirname
import click
import logging
import sys
from monitoring_consumer import monitoring_consumer
from monitoring_producer import monitoring_producer
from config import get_pg_connection
from sql_queries import configure_monitoring_database


@click.command()
@click.argument('config_path', type=click.Path(exists=True))
def start_consumer(config_path: str) -> None:
    """Start the monitoring consumer"""
    monitoring_consumer(config_path)


@click.command()
@click.argument('config_path', type=click.Path(exists=True))
@click.argument('id', type=int)
def start_producer(config_path: str, id: int) -> None:
    """Start the monitoring producer"""
    monitoring_producer(config_path, id)


@click.group()
def main(args=None) -> None:
    """Utility to run the website monitoring commands."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)


@click.command()
@click.argument('config_path', type=click.Path(exists=True))
def configure_database(config_path: str) -> None:
    """Prepare the database from scratch for the consumer and producer"""
    conn = get_pg_connection(config_path)
    configure_monitoring_database(conn)
    conn.close()


main.add_command(start_consumer)
main.add_command(start_producer)
main.add_command(configure_database)


if __name__ == "__main__":
    sys.exit(main())
