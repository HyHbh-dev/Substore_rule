import ipaddress
from pathlib import Path

from loguru import logger


# 读取ip4.txt文件
def read_ip4_txt(path: Path) -> list[str]:
    with open(path, "r") as f:
        logger.info(f"读取ip4.txt文件,ip数量为{len(f.read().splitlines())}")
        # 如果文件不存在抛出异常
        if not path.exists():
            # todo: 编写调用函数下载ip4.txt文件
            raise FileNotFoundError("ip4.txt文件不存在")
        return f.read().splitlines()


# 转换广播地址为ip地址
def cidr_to_all_ips(cidr: str) -> list[str]:
    network = ipaddress.ip_network(cidr, strict=False)
    return [str(ip) for ip in network.hosts()]


# 判断数据为ip还是ip区间,ip区间的话转换为ip地址
def is_ip_range(ip_range: list[str]) -> list[str]:
    ip_list = []
    logger.info("开始转换ip区间为ip地址")
    for ip in ip_range:
        if "/" in ip:
            ip_list.append(cidr_to_all_ips(ip))
        else:
            ip_list.append(ip)
    logger.info(f"转换完成,ip数量为{len(ip_list)}")
    return ip_list
