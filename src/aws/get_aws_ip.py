# 从aws官网获取ip_ranges.json文件
# 这个文件是从aws获取ip并筛选ipv4
# 并筛选出亚太和美西地区IP地址
import asyncio
import json

import aiohttp
from loguru import logger
from pydantic import BaseModel

from src.constants import AWS_BASE_URL, REGIONS


class IpRangeInfo4(BaseModel):
    ip_prefix: str
    region: str
    service: str
    network_border_group: str


class IpRangeInfo6(BaseModel):
    ipv6_prefix: str
    region: str
    service: str
    network_border_group: str


class IpRange(BaseModel):
    prefixes: list[IpRangeInfo4]
    ipv6_prefixes: list[IpRangeInfo6]
    syncToken: str
    createDate: str


# 获取aws的ip_ranges
async def get_aws_ip_ranges(aws_url: str = AWS_BASE_URL) -> IpRange:
    async with aiohttp.ClientSession() as session:
        logger.info("开始获取aws的ip_ranges")
        async with session.get(aws_url) as resp:
            if resp.status != 200:
                error_msg = f"无法获取aws的ip_ranges: {resp.status}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            data = await resp.json()
            # 并保存到文件
            with open("ip_ranges.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("成功获取aws的ip_ranges")
            return IpRange(**data)


# 传入数据并筛选地区ipv4
def filter_ipv4_only_ip(all_data: list[IpRangeInfo4]) -> list[str]:
    return [ip.ip_prefix for ip in all_data if ip.region in REGIONS]


# 写入文件ip4.txt
def write_to_file(all_data: list[str]) -> list[str]:
    logger.info("开始写入文件")
    with open("ip4.txt", "w") as f4:
        for prefix in all_data:
            f4.write(prefix + "\n")
    logger.info("成功写入文件")
    return all_data


def get_data():
    ip_range = asyncio.run(get_aws_ip_ranges())
    ip4_list = filter_ipv4_only_ip(ip_range.prefixes)
    write_to_file(ip4_list)
