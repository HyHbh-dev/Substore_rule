from get_aws_ip import get_aws_ip_ranges

import asyncio

if __name__ == "__main__":
    ip_ranges = asyncio.run(get_aws_ip_ranges())
