from PyQt5.QtSql import QSqlDatabase, QSqlQuery, QSqlTableModel

from src.utility_functions.database_settings import DatabaseSettings


class DatabaseManager:
    def __init__(self, database_settings: DatabaseSettings):
        self.settings = database_settings
        self.db = None
        self.connected = False

        # Decide which driver to use based on the database type
        if self.settings.database_type.lower() == "sqlite":
            self.driver = "QSQLITE"
        elif self.settings.database_type.lower() == "postgresql":
            self.driver = "QPSQL"

        # Check if the driver is available
        if not QSqlDatabase.isDriverAvailable(self.driver):
            raise Exception(f"Database driver {self.settings.database_type} is not available.")

        self.connect()

    def connect(self):
        # Create a database connection
        self.db = QSqlDatabase.addDatabase(self.driver)
        self.db.setHostName(self.settings.host)
        self.db.setPort(self.settings.port)
        self.db.setUserName(self.settings.username)
        self.db.setPassword(self.settings.password)
        self.db.setDatabaseName(self.settings.database_name)

        if not self.db.open():
            print("Error:", self.db.lastError().text())
            self.connected = False
        else:
            self.connected = True

    def create_table(self, table_name, fields):
        query = QSqlQuery(self.db)
        query.exec(f"CREATE TABLE IF NOT EXISTS {table_name} ({fields})")

    def get_table(self, table_name):
        query = QSqlQuery(self.db)
        query.exec(f"SELECT * FROM {table_name}")

        model = QSqlTableModel()
        model.setTable(table_name)
        model.setEditStrategy(QSqlTableModel.OnManualSubmit)
        model.select()

        return model

    def update_table(self, table_name, data_dict, condition_column, condition_value):
        query = QSqlQuery(self.db)

        # Construct the UPDATE query
        update_query = f"UPDATE {table_name} SET "
        update_query += ', '.join([f"{key} = '{value}'" for key, value in data_dict.items()])
        update_query += f" WHERE {condition_column} = '{condition_value}'"

        query.exec(update_query)

        # Commit the changes to make them permanent
        self.db.commit()

    def delete_table(self, table_name):
        query = QSqlQuery(self.db)
        query.exec(f"DROP TABLE IF EXISTS {table_name}")

    def delete_database(self):
        if self.connected:
            self.db.close()

        # Remove the database connection
        QSqlDatabase.removeDatabase(self.db.connectionName())
