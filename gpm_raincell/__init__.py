"""GPM DPR 雨团识别的公共算法接口。"""

from .identify import connect_time, identify_rc, region_mask

__all__ = ["connect_time", "identify_rc", "region_mask"]
