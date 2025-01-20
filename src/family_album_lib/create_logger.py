from logging import Logger, DEBUG, Formatter, FileHandler
import os


class CustomLogger(Logger):

    def __init__(self, app_name: str, version: str, log_level: int = DEBUG) -> None:
        super().__init__(app_name, log_level)
        self.__app_name = app_name
        self.__version = version
        self.__log_level = log_level
        self.__setup_logger()

    def __setup_logger(self) -> None:
        # Get the user's home directory
        home_dir = os.path.expanduser("~")
        # Create the log directory path
        log_dir = os.path.join(home_dir, self.__app_name, "logs")
        # Ensure the log directory exists
        os.makedirs(log_dir, exist_ok=True)
        # Define the log file path
        log_file = os.path.join(log_dir, f"{self.__app_name}_ver.{self.__version}.log")

        # Create a file handler
        file_handler = FileHandler(log_file)
        file_handler.setLevel(self.__log_level)

        # Create a formatter and set it for the handler
        formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)

        # Add the handler to the logger
        self.addHandler(file_handler)

    def __call__(self, message: str, log_level: int = 0) -> None:
        if log_level == 0:
            log_level = self.__log_level
        self.log(log_level, message)

    def log_error(self, message: str) -> None:
        self.error(message)

    def log_warning(self, message: str) -> None:
        self.warning(message)

    def log_info(self, message: str) -> None:
        self.info(message)

    def log_critical(self, message: str) -> None:
        self.critical(message)

    def log_debug(self, message: str) -> None:
        self.debug(message)
