from loguru import logger

from get_aws_ip import get_data

logger.add("file_{time}.log", rotation="500 MB")


if __name__ == "__main__":
    logger.info("启动")
    get_data()
