"""历史多年份入口；统一递归处理，不再硬编码年份和服务器路径。

示例：python DPRtoRCmultiyears.py --input "D:/GPM" --output "D:/rc_data"
推荐使用 python -m gpm_raincell，参数完全相同。
"""

from gpm_raincell.batch import main

if __name__ == "__main__":
    raise SystemExit(main())
