from typing import Dict, List
import pytest
from src.monitoring_consumer import insert_monitoring_metrics, consumer_main_loop
import sys
sys.path.append('<project directory>')

class MockedMessage(object):
    def __init__(self, value) -> None:
        self.value = value


class MockedConsumer(object):
    def __init__(self, messages: List[Dict], failing=False) -> None:
        self.messages = [MockedMessage(m) for m in messages]
        self.failing = failing
        self.commit_count = 0

    def __iter__(self):
        return iter(self.messages)

    def commit(self):
        self.commit_count += 1
        if self.failing:
            raise Exception


def test_insert_monitoring_metrics(mocker):
    mocked_rsq = mocker.patch('src.monitoring_consumer.run_sql_query')
    metrics = {"unix_timestamp": 1, "returned_code": 402,
               "response_time": 50, "regexp": None}
    sql_query = "INSERT INTO website_availability.availability_monitor_metrics " \
                "(amm_unix_timestamp, amd_response_code, amd_response_time, amm_regexp_found) " \
                "VALUES (1, 402, 50, NULL);"

    insert_monitoring_metrics("connection", [metrics, metrics])

    mocked_rsq.assert_called_with("connection", sql_query + sql_query)
    assert (insert_monitoring_metrics("connection", []))


def test_consumer_main_loop_happy_path(mocker):
    fake_connection = ""
    sample_message = {'unix_timestamp': 1,
                      'returned_code': 200, 'response_time': 1, 'regexp': None}
    mocked_consumer = MockedConsumer([sample_message, sample_message])
    mocked_insert_monitoring_metrics = mocker.patch(
        'src.monitoring_consumer.insert_monitoring_metrics', return_value=True)

    consumer_main_loop(fake_connection, mocked_consumer, 0)

    expected_insert_monitoring_argument = [
        {'unix_timestamp': 1, 'returned_code': 200, 'response_time': 1, 'regexp': None}, {
            'unix_timestamp': 1, 'returned_code': 200, 'response_time': 1, 'regexp': None}]
    mocked_insert_monitoring_metrics.assert_called_with(
        fake_connection, expected_insert_monitoring_argument)


def test_consumer_main_loop_failing_commit(mocker, caplog):
    with pytest.raises(RuntimeError):
        fake_connection = ""
        sample_message = {'unix_timestamp': 1,
                          'returned_code': 200, 'response_time': 1, 'regexp': None}
        mocked_consumer = MockedConsumer(
            [sample_message, sample_message], failing=True)
        mocker.patch(
            'src.monitoring_consumer.insert_monitoring_metrics', return_value=True)

        consumer_main_loop(fake_connection, mocked_consumer, 0)

    assert (mocked_consumer.commit_count == 10)
    assert ("Unexpected error trying to commit: " in caplog.text)


def exception_side_effect():
    raise Exception("Test")


def test_consumer_main_loop_failing_database_write(mocker, caplog):
    with pytest.raises(RuntimeError):
        fake_connection = ""
        sample_message_1 = {'unix_timestamp': 1,
                            'returned_code': 200, 'response_time': 1, 'regexp': None}
        sample_message_2 = {'unix_timestamp': 1,
                            'returned_code': 200, 'response_time': 1, 'regexp': True}
        mocked_consumer = MockedConsumer(
            [sample_message_1, sample_message_2])
        mocked_insert = mocker.patch(
            'src.monitoring_consumer.insert_monitoring_metrics')
        mocked_insert.side_effect = exception_side_effect

        consumer_main_loop(fake_connection, mocked_consumer, 0)

    assert (mocked_consumer.commit_count == 0)
    assert ("Unexpected error inserting monitoring metrics: " in caplog.text)


def test_consumer_no_messages(mocker):
    fake_connection = ""
    mocked_consumer = MockedConsumer([])
    mocker.patch(
        'src.monitoring_consumer.insert_monitoring_metrics', return_value=True)

    main_loop = consumer_main_loop(fake_connection, mocked_consumer, 0)
    assert (not main_loop)
