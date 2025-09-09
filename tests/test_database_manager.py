import unittest

from PyQt6.QtWidgets import QApplication
from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase

from src.family_album.utility_functions.database_manager import DatabaseManager
from src.family_album.utility_functions.database_settings import DatabaseSettings


class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        # SQLite settings
        self.sqlite_settings = DatabaseSettings(
            database_type="sqlite",
            host="",  # SQLite does not use host
            port=0,   # SQLite does not use port
            username="",
            password="",
            database_name="test_db.sqlite"
        )

        # PostgreSQL settings (provide your actual PostgreSQL credentials)
        self.postgres_settings = DatabaseSettings(
            database_type="postgresql",
            host="localhost",
            port=5432,
            username="your_username",
            password="your_password",
            database_name="test_db_postgres"
        )

        # Initialize the application to work with PyQt
        self.app = QApplication([])

        # Check available database drivers
        print(QSqlDatabase.drivers())
        # Ensure PostgreSQL driver is available
        assert "QPSQL" in QSqlDatabase.drivers()

    def tearDown(self):
        # Clean up and close the application
        self.app.quit()

    def test_connect_sqlite(self):
        db_manager = DatabaseManager(self.sqlite_settings)
        self.assertTrue(db_manager.connected)
        db_manager.delete_database()  # Clean up after the test

    def test_create_table_sqlite(self):
        db_manager = DatabaseManager(self.sqlite_settings)
        db_manager.create_table("test_table", "id INTEGER PRIMARY KEY, name TEXT")
        db_manager.delete_database()  # Clean up after the test

    def test_connect_postgresql(self):
        ...
        # db_manager = DatabaseManager(self.postgres_settings)
        # self.assertTrue(db_manager.connected)
        # db_manager.delete_database()  # Clean up after the test

    def test_create_table_postgresql(self):
        ...
        # db_manager = DatabaseManager(self.postgres_settings)
        # db_manager.create_table("test_table", "id SERIAL PRIMARY KEY, name VARCHAR(255)")
        # db_manager.delete_database()  # Clean up after the test

    def test_get_table_data(self):
        # Assuming you have a table named 'test_table' with some data
        db_manager = DatabaseManager(self.sqlite_settings)
        data = db_manager.get_table("test_table")
        self.assertIsInstance(data, QSqlQueryModel)
        db_manager.delete_database()  # Clean up after the test


if __name__ == '__main__':
    unittest.main()
