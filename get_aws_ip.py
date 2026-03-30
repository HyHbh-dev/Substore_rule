# 从aws官网获取ip_ranges.json文件
# 命令为curl -O https://ip-ranges.amazonaws.com/ip-ranges.json
# 使用异步请求且必须获取到，否则panic
import aiohttp

async def get_aws_ip_ranges():
    url = "https://ip-ranges.amazonaws.com/ip-ranges.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to get AWS IP ranges: {resp.status}")
            # 并保存到文件
            with open("ip_ranges.json", "w") as f:
                f.write(await resp.text())
            return await resp.json()

