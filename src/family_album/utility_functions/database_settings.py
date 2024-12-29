class DatabaseSettings:
    def __init__(self, database_type, host, port, username, password, database_name):
        self.database_type = database_type
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database_name = database_name
