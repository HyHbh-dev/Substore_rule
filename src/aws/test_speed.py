"""使用tcping和httping测试延迟"""

import asyncio
import time
from dataclasses import dataclass

import httpx
from loguru import logger

from src.constants import DOWNLOAD_URL


@dataclass
class TcpingResult:
    host: str
    port: int
    latency_ms: float | None
    success: bool


@dataclass
class HttpingResult:
    host: str
    port: int
    status_code: int | None
    latency_ms: float | None
    size_bytes: int | None
    success: bool


@dataclass
class SpeedResult:
    ip: str
    host: str
    latency_ms: float | None
    speed_mbps: float | None  # 下载速度 MB/s
    success: bool


# tcping
async def tcping(host: str, port: int = 443, timeout: float = 3.0) -> TcpingResult:
    try:
        loop = asyncio.get_event_loop()
        start = loop.time()
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        latency = (loop.time() - start) * 1000
        writer.close()
        await writer.wait_closed()
        return TcpingResult(host, port, round(latency, 2), True)
    except Exception as e:
        logger.warning(f"TCPing 失败 {host}:{port} - {e}")
        return TcpingResult(host, port, None, False)


# httping
async def httping(url: str, timeout: float = 3.0) -> HttpingResult:
    try:
        async with httpx.AsyncClient() as client:
            start = time.perf_counter()
            response = await client.get(url, timeout=timeout)
            latency = (time.perf_counter() - start) * 1000
            return HttpingResult(
                url=url,
                status_code=response.status_code,
                latency_ms=round(latency, 2),
                size_bytes=len(response.content),
                success=True,
            )
    except Exception as e:
        logger.warning(f"HTTPing 失败 {url} - {e}")
        return HttpingResult(url, None, None, None, False)


# 批量测试
async def batch_tcping(hosts: list[str], timeout: float = 3.0) -> list[TcpingResult]:
    logger.info(f"开始tcping测试,ip数量为{len(hosts)}")
    tasks = [tcping(host, 443, timeout) for host in hosts]
    return await asyncio.gather(*tasks)


# 批量测试
async def batch_httping(urls: list[str], timeout: float = 3.0) -> list[HttpingResult]:
    logger.info(f"开始httping测试,url数量为{len(urls)}")
    tasks = [httping(url, timeout) for url in urls]
    return await asyncio.gather(*tasks)


# 过滤延迟为none和大于200的IP地址
def delay_filtering(ip_list: list[TcpingResult | HttpingResult]) -> list:
    ip_list_filtered = []
    for ip in ip_list:
        if ip.latency_ms is not None and ip.latency_ms < 200:
            ip_list_filtered.append(ip.host)
    return ip_list_filtered


# 测试下载速度
async def test_download_speed(
    ip: str,
    host: str,
    path: str = "/",
    port: int = 443,
    timeout: float = 10.0,
) -> SpeedResult:
    url = f"https://{ip}{path}"
    headers = {"Host": host}  # 关键：Host 头设置为域名

    try:
        async with httpx.AsyncClient(
            verify=False
        ) as client:  # verify=False 跳过证书校验
            start = time.perf_counter()
            async with client.stream(
                "GET", url, headers=headers, timeout=timeout
            ) as response:
                latency = (time.perf_counter() - start) * 1000
                total_bytes = 0
                download_start = time.perf_counter()
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    total_bytes += len(chunk)
                elapsed = time.perf_counter() - download_start

        speed_mbps = (total_bytes / elapsed) / (1024 * 1024) if elapsed > 0 else 0
        return SpeedResult(ip, host, round(latency, 2), round(speed_mbps, 2), True)

    except Exception as e:
        logger.warning(f"测速失败 {ip} - {e}")
        return SpeedResult(ip, DOWNLOAD_URL, None, None, False)


# 批量测试
async def batch_speed_test(
    ips: list[str],
    host: str,
    path: str = "/",
) -> list[SpeedResult]:
    logger.info(f"开始批量测速,ip数量为{len(ips)}")
    tasks = [test_download_speed(ip, host, path) for ip in ips]
    results = await asyncio.gather(*tasks)
    # 按速度排序
    return sorted(results, key=lambda r: r.speed_mbps or 0, reverse=True)
