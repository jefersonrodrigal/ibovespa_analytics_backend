from src.storage import db


def test_connection_to_test_database_succeeds():
    assert db.check_connection(for_tests=True) is True
