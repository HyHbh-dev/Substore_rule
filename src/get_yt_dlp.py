import platform
from pathlib import Path

import httpx
from loguru import logger

from src.constants import YTDLP_GITHUB_API


def get_download_url(assets: list[dict]) -> str | None:
    system = platform.system()
    machine = platform.machine()

    match system:
        case "Windows":
            filename = "yt-dlp.exe"
        case "Darwin":
            filename = "yt-dlp_macos" if machine == "arm64" else "yt-dlp_macos_legacy"
        case "Linux":
            filename = (
                "yt-dlp_linux_aarch64" if machine == "aarch64" else "yt-dlp_linux"
            )
        case _:
            logger.error(f"不支持的操作系统: {system}")
            return None

    for asset in assets:
        if asset["name"] == filename:
            return asset["browser_download_url"]

    return None


async def download_yt_dlp(save_dir: Path = Path("bin")) -> Path | None:
    save_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as client:
        logger.info("获取最新版本信息")
        response = await client.get(YTDLP_GITHUB_API, timeout=30)
        response.raise_for_status()
        release = response.json()

    url = get_download_url(release["assets"])
    if url is None:
        return None

    filename = url.split("/")[-1]
    save_path = save_dir / filename

    logger.info(f"开始下载: {filename}")
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url, timeout=60) as response:
            response.raise_for_status()
            with open(save_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

    # Linux/macOS 需要添加可执行权限
    if platform.system() != "Windows":
        save_path.chmod(0o755)

    logger.info(f"下载完成: {save_path}")
    return save_path
