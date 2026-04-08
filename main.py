import asyncio
import ipaddress
import json
import os
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

from src.aws.get_aws_ip import filter_ipv4_only_ip, get_aws_ip_ranges
from src.aws.test_speed import batch_speed_test, batch_tcping
from src.constants import DOWNLOAD_URL

logger.add("file_{time}.log", rotation="500 MB")
RESULT_JSON_PATH = Path("fastest_ips.json")


def get_first_usable_ip(cidr: str) -> str | None:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        return next((str(ip) for ip in network.hosts()), None)
    except ValueError as exc:
        logger.warning(f"无效CIDR {cidr}: {exc}")
        return None


def sample_ips_from_cidr(cidr: str, sample_size: int) -> list[str]:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        logger.warning(f"无效CIDR {cidr}: {exc}")
        return []

    if sample_size <= 0:
        return []

    if network.version != 4:
        logger.warning(f"暂不处理非 IPv4 网段: {cidr}")
        return []

    if network.prefixlen == 32:
        return [str(network.network_address)]
    if network.prefixlen == 31:
        return [str(network.network_address), str(network.broadcast_address)][
            :sample_size
        ]

    start = int(network.network_address) + 1
    end = int(network.broadcast_address) - 1
    total_hosts = end - start + 1
    actual_size = min(sample_size, total_hosts)

    if actual_size == 1:
        return [str(ipaddress.ip_address(start))]

    sampled_ints = []
    span = end - start
    for index in range(actual_size):
        offset = round(index * span / (actual_size - 1))
        sampled_ints.append(start + offset)

    # 四舍五入可能导致重复，这里补齐成唯一 IP 集合
    unique_ints = list(dict.fromkeys(sampled_ints))
    current = start
    while len(unique_ints) < actual_size and current <= end:
        if current not in unique_ints:
            unique_ints.append(current)
        current += 1

    return [str(ipaddress.ip_address(ip)) for ip in unique_ints]


def build_speed_candidates(
    cidr_list: list[str], range_limit: int, sample_size: int
) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    for cidr in cidr_list[:range_limit]:
        ips = sample_ips_from_cidr(cidr, sample_size) if "/" in cidr else [cidr]
        if not ips:
            fallback_ip = get_first_usable_ip(cidr) if "/" in cidr else cidr
            if fallback_ip is None:
                continue
            ips = [fallback_ip]

        for ip in ips:
            candidates.append((cidr, ip))

    return candidates


def pick_low_latency_ip_per_cidr(
    results: list, cidr_by_ip: dict[str, str], latency_limit_ms: float
) -> list:
    best_by_cidr = {}

    for result in results:
        if not result.success or result.latency_ms is None:
            continue
        if result.latency_ms > latency_limit_ms:
            continue

        cidr = cidr_by_ip.get(result.host, result.host)
        current_best = best_by_cidr.get(cidr)
        if current_best is None or result.latency_ms < (current_best.latency_ms or float("inf")):
            best_by_cidr[cidr] = result

    return sorted(
        best_by_cidr.values(), key=lambda item: item.latency_ms or float("inf")
    )


def pick_best_result_per_cidr(results: list, cidr_by_ip: dict[str, str]) -> list:
    best_by_cidr = {}

    for result in results:
        if not result.success or result.speed_mbps is None:
            continue
        cidr = cidr_by_ip.get(result.ip, result.ip)
        current_best = best_by_cidr.get(cidr)
        if current_best is None or (result.speed_mbps or 0) > (
            current_best.speed_mbps or 0
        ):
            best_by_cidr[cidr] = result

    return sorted(
        best_by_cidr.values(), key=lambda item: item.speed_mbps or 0, reverse=True
    )


def write_results_to_json(
    best_results: list, cidr_by_ip: dict[str, str], latency_by_cidr: dict[str, float]
) -> Path:
    payload = {
        "best_ip": None,
        "ranges": [],
    }

    for result in best_results:
        payload["ranges"].append(
            {
                "cidr": cidr_by_ip.get(result.ip, result.ip),
                "best_latency_ms": latency_by_cidr.get(
                    cidr_by_ip.get(result.ip, result.ip)
                ),
                **asdict(result),
            }
        )

    if payload["ranges"]:
        payload["best_ip"] = payload["ranges"][0]

    RESULT_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return RESULT_JSON_PATH


async def get_fastest_ip() -> dict | None:
    url = urlparse(DOWNLOAD_URL)
    host = url.netloc
    path = url.path or "/"
    max_test_ranges = int(os.getenv("MAX_TEST_RANGES", "30"))
    sample_ips_per_range = int(os.getenv("SAMPLE_IPS_PER_RANGE", "3"))
    latency_limit_ms = float(os.getenv("LATENCY_LIMIT_MS", "200"))

    logger.info("开始获取 AWS IP 段")
    ip_range = await get_aws_ip_ranges()
    cidr_list = filter_ipv4_only_ip(ip_range.prefixes)
    logger.info(f"共筛选出 {len(cidr_list)} 个 IPv4 网段")

    candidates = build_speed_candidates(
        cidr_list, max_test_ranges, sample_ips_per_range
    )
    if not candidates:
        logger.error("没有可用于测速的 IP")
        return None

    logger.info(
        f"准备测速 {min(len(cidr_list), max_test_ranges)} 个网段，共 {len(candidates)} 个候选 IP"
    )
    cidr_by_ip = {ip: cidr for cidr, ip in candidates}

    tcping_results = await batch_tcping([ip for _, ip in candidates])
    low_latency_results = pick_low_latency_ip_per_cidr(
        tcping_results, cidr_by_ip, latency_limit_ms
    )

    if not low_latency_results:
        logger.error("没有通过延迟筛选的 IP")
        return None

    selected_ips = [result.host for result in low_latency_results]
    latency_by_cidr = {
        cidr_by_ip[result.host]: result.latency_ms
        for result in low_latency_results
        if result.latency_ms is not None
    }
    logger.info(
        f"延迟筛选后剩余 {len(selected_ips)} 个网段，开始下载测速"
    )

    results = await batch_speed_test(selected_ips, host, path)
    valid_results = pick_best_result_per_cidr(results, cidr_by_ip)

    if not valid_results:
        logger.error("没有获取到有效测速结果")
        return None

    best_result = valid_results[0]
    best_payload = {
        "cidr": cidr_by_ip.get(best_result.ip, best_result.ip),
        "ip": best_result.ip,
        "host": best_result.host,
        "latency_ms": best_result.latency_ms,
        "speed_mbps": best_result.speed_mbps,
        "success": best_result.success,
    }
    output_path = write_results_to_json(valid_results, cidr_by_ip, latency_by_cidr)
    logger.success(f"最快 IP: {best_payload}")
    logger.info(f"测速结果已写入 {output_path}")

    for result in valid_results[:10]:
        logger.info(
            {
                "cidr": cidr_by_ip.get(result.ip, result.ip),
                **asdict(result),
            }
        )

    return best_payload


if __name__ == "__main__":
    logger.info("启动测速")
    fastest_ip = asyncio.run(get_fastest_ip())
    if fastest_ip is None:
        raise SystemExit(1)
