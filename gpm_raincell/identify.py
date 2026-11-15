"""GPM DPR 雨团识别：时间读取、研究区筛选和八邻域连通搜索。"""

from collections import deque
import operator

import numpy as np


DEFAULT_EXTENTS = (95.0, 145.0, -5.0, 35.0)
DEFAULT_THRESHOLD = 0.5
DEFAULT_MIN_PIXELS = 4


def connect_time(f):
    """读取 FS/ScanTime，返回逐扫描的 datetime64[h] 数组（保留旧接口）。"""
    scan_time = f["FS/ScanTime"]
    values = [scan_time[name][:] for name in ("Year", "Month", "DayOfMonth", "Hour")]
    date_strings = [
        f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}"
        for year, month, day, hour in zip(*values)
    ]
    return np.asarray(date_strings, dtype="datetime64[h]")


def region_mask(lat, lon, mid=True, extents=DEFAULT_EXTENTS):
    """返回研究区掩码，范围顺序为西、东、南、北，含边界。

    mid=True 时用中间波束判断整条扫描，返回 (nscan,)；
    mid=False 时逐像元判断，返回 (nscan, nray)。不处理跨日期变更线范围。
    """
    lat, lon = np.asarray(lat), np.asarray(lon)
    if lat.ndim != 2 or lat.shape != lon.shape or lat.shape[1] == 0:
        raise ValueError("lat 和 lon 必须是形状相同且含有波束的二维数组")
    bounds = np.asarray(extents, dtype=float)
    if bounds.shape != (4,) or not np.isfinite(bounds).all():
        raise ValueError("extents 必须包含四个有限数值：西、东、南、北")
    west, east, south, north = bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("经度范围应在 [-180, 180]、纬度范围应在 [-90, 90] 内且从小到大排列")
    if mid:
        middle = lat.shape[1] // 2
        lat, lon = lat[:, middle], lon[:, middle]
    return (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north)


def identify_rc(pr_s, rcid=None, *, threshold=DEFAULT_THRESHOLD,
                min_pixels=DEFAULT_MIN_PIXELS):
    """按八邻域识别二维近地面降雨率中的雨团。

    有限且 >= threshold (mm/h) 的像元参与搜索；保留至少 min_pixels 个
    像元的连通分量。编号按行优先首次出现的顺序从 1 开始，背景为 0。
    不修改 pr_s。提供 rcid 时将其清零并原位写入，返回同一数组，兼容旧调用。
    未提供 rcid 时返回 int32 标签数组。最小像元数不是面积阈值。
    """
    pr_s = np.asarray(pr_s)
    if pr_s.ndim != 2:
        raise ValueError("pr_s 必须是二维数组")
    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError("threshold 必须是非负有限数值")
    try:
        min_pixels = operator.index(min_pixels)
    except TypeError as exc:
        raise ValueError("min_pixels 必须是正整数") from exc
    if min_pixels < 1:
        raise ValueError("min_pixels 必须是正整数")

    if rcid is None:
        rcid = np.zeros(pr_s.shape, dtype=np.int32)
    else:
        if not isinstance(rcid, np.ndarray) or rcid.shape != pr_s.shape:
            raise ValueError("rcid 必须是与 pr_s 形状相同的 NumPy 数组")
        if rcid.dtype.kind not in "if" or rcid.dtype.itemsize < 4:
            raise ValueError("rcid 必须使用至少 32 位的有符号整数或浮点类型")
        if np.shares_memory(pr_s, rcid):
            raise ValueError("rcid 不能与 pr_s 共享内存")
        rcid.fill(0)

    remaining = np.isfinite(pr_s) & (pr_s >= threshold)
    nscan, nray = pr_s.shape
    label = 0
    for row, col in np.argwhere(remaining):
        if not remaining[row, col]:
            continue
        remaining[row, col] = False
        queue = deque([(row, col)])
        component = []
        while queue:
            r, c = queue.popleft()
            component.append((r, c))
            for rr in range(max(0, r - 1), min(nscan, r + 2)):
                for cc in range(max(0, c - 1), min(nray, c + 2)):
                    if remaining[rr, cc]:
                        remaining[rr, cc] = False
                        queue.append((rr, cc))
        if len(component) >= min_pixels:
            label += 1
            rows, cols = np.asarray(component).T
            rcid[rows, cols] = label
    return rcid
