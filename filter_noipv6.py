# 读取json文件
import json


# 接受路劲为参数
async def filter_no_ipv6(path):
    with open("ip_ranges.json", "r") as f:
        data = json.load(f)
        # 保存f.prefixers的结果
        prefixes = data["prefixes"]
        with open("no_ipv6.json", "w") as no6:
            no6.write(await prefixes.text())
