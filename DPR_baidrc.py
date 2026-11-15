"""历史命令行入口；推荐使用 python -m gpm_raincell。

示例：python DPR_baidrc.py --input "D:/GPM" --output "D:/rc_data"
导入本模块不会开始读取数据或创建输出。
"""

from gpm_raincell.batch import main

if __name__ == "__main__":
    raise SystemExit(main())
