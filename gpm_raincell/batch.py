"""GPM 2ADPR V07 HDF5 → 雨团 NetCDF 的统一批处理入口。"""

import argparse
import logging
import os
from pathlib import Path
import sys
import tempfile

import h5py
import numpy as np
import xarray as xr

from .identify import (
    DEFAULT_EXTENTS,
    DEFAULT_MIN_PIXELS,
    DEFAULT_THRESHOLD,
    connect_time,
    identify_rc,
    region_mask,
)


LOGGER = logging.getLogger(__name__)
HDF5_SUFFIXES = {".hdf5", ".h5"}
PROFILE_FIELDS = {
    "hst": ("FS/PRE/heightStormTop", ("nscan", "nray")),
    "typePrecip": ("FS/CSF/typePrecip", ("nscan", "nray")),
    "pr3d": ("FS/SLV/precipRate", ("nscan", "nray", "nbin")),
    "R": ("FS/SLV/zFactorFinal", ("nscan", "nray", "nbin", "nfreq")),
    "dsd": ("FS/SLV/paramDSD", ("nscan", "nray", "nbin", "nDSD")),
}


def build_dataset(source, *, threshold=DEFAULT_THRESHOLD,
                  min_pixels=DEFAULT_MIN_PIXELS, extents=DEFAULT_EXTENTS):
    """读取单个 HDF5，返回已载入内存的 Dataset；无区域交集/雨团时返回 None。

    所有廓线字段均为必需字段，不自动将双频数据降为单频。文件句柄在函数返回前关闭。
    """
    source = Path(source)
    with h5py.File(source, "r") as handle:
        lat = handle["FS/Latitude"][:]
        lon = handle["FS/Longitude"][:]
        mask = region_mask(lat, lon, extents=extents)
        if not mask.any():
            return None
        prs = handle["FS/SLV/precipRateNearSurface"][:]
        if prs.shape != lat.shape:
            raise ValueError("precipRateNearSurface 与 Latitude 的形状不一致")
        prs = prs.astype(np.result_type(prs.dtype, np.float32), copy=True)
        prs[~mask] = np.nan
        prs[~np.isfinite(prs) | (prs < threshold)] = np.nan

        # 在原始扫描网格中识别，避免裁切后把不连续的扫描行错误连接起来。
        labels = identify_rc(prs, threshold=threshold, min_pixels=min_pixels)
        if not labels.any():
            return None
        labels = labels[mask].astype(np.float64)
        labels[labels == 0] = np.nan
        times = connect_time(handle)[mask]
        variables = {
            "time": times[0],
            "lat": (("nscan", "nray"), lat[mask]),
            "lon": (("nscan", "nray"), lon[mask]),
            "rcid": (("nscan", "nray"), labels),
            "prs": (("nscan", "nray"), prs[mask]),
        }
        indices = np.flatnonzero(mask)
        breaks = np.flatnonzero(np.diff(indices) > 1) + 1
        sections = np.split(indices, breaks)
        for name, (path, dims) in PROFILE_FIELDS.items():
            data = handle[path]
            if data.ndim != len(dims) or data.shape[:2] != lat.shape:
                raise ValueError(f"{path} 维度不符合预期 {dims}，实际形状为 {data.shape}")
            # 逐段读取，仅将选中扫描行的三维/四维数据载入内存。
            selected = np.concatenate(
                [data[int(section[0]):int(section[-1]) + 1] for section in sections], axis=0
            )
            variables[name] = (dims, selected)

    ds = xr.Dataset(variables)
    ds = ds.assign_coords({name: np.arange(size) for name, size in ds.sizes.items()})
    ds["scan_index"] = ("nscan", np.flatnonzero(mask))
    ds["scan_time"] = ("nscan", times)
    ds["rcid"].attrs.update(
        long_name="Rain cluster identifier (local to this granule)",
        description="1-based labels; NaN denotes background or rejected small components",
    )
    ds["prs"].attrs.update(units="mm h-1", long_name="Near-surface precipitation rate")
    ds["lat"].attrs["units"] = "degrees_north"
    ds["lon"].attrs["units"] = "degrees_east"
    ds["scan_index"].attrs["description"] = "Zero-based scan index in source granule"
    ds["time"].attrs["description"] = "First selected scan time, truncated to the hour"
    ds["scan_time"].attrs["description"] = "Selected scan times, truncated to the hour"
    ds.attrs.update(
        source_file=source.name,
        precipitation_threshold_mm_h=float(threshold),
        min_pixels=int(min_pixels),
        connectivity=8,
        region_extents=np.asarray(extents, dtype=float),
        region_selection="Entire scan selected by its middle beam; inclusive boundaries",
        time_precision="hour (legacy convention; minutes and seconds are not read)",
    )
    return ds


def process_file(source, destination, *, overwrite=False, **options):
    """处理一个颗粒文件；返回 written、existing 或 empty，不覆盖已有结果（默认）。"""
    destination = Path(destination)
    if Path(source).resolve() == destination.resolve():
        raise ValueError("输出路径不能与输入文件相同")
    if destination.exists() and not destination.is_file():
        raise ValueError(f"输出路径已存在但不是文件：{destination}")
    if destination.exists() and not overwrite:
        return "existing"
    ds = build_dataset(source, **options)
    if ds is None:
        return "empty"
    temporary = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # 先写同目录临时文件，写入成功再替换目标，避免留下半个 NetCDF。
        with tempfile.NamedTemporaryFile(
            prefix=".rain-cell-", suffix=".nc", dir=destination.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
        ds.to_netcdf(temporary, engine="netcdf4")
        os.replace(temporary, destination)
    finally:
        ds.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "written"


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="单个 HDF5 文件或递归搜索的输入目录")
    parser.add_argument("--output", type=Path, required=True, help="NetCDF 输出目录")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="近地面降雨率阈值 mm/h，包含等号（默认 0.5）")
    parser.add_argument("--min-pixels", type=int, default=DEFAULT_MIN_PIXELS,
                        help="雨团最小像元数，包含等号（默认 4）")
    parser.add_argument("--extent", type=float, nargs=4, default=DEFAULT_EXTENTS,
                        metavar=("WEST", "EAST", "SOUTH", "NORTH"),
                        help="研究区西、东、南、北边界（默认 95 145 -5 35）")
    parser.add_argument("--overwrite", action="store_true", help="重新计算并替换同名输出")
    parser.add_argument("--verbose", action="store_true", help="报错时显示完整调用栈")
    return parser


def main(argv=None):
    # Windows 重定向到管道时可能默认 cp1252，无法输出中文帮助和日志。
    # 所有命令行入口统一输出 UTF-8；不依赖 CI/终端预设的编码环境变量。
    # 嵌入调用时兼容没有 reconfigure 方法的 StringIO 等捕获流。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = make_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    options = dict(threshold=args.threshold, min_pixels=args.min_pixels, extents=args.extent)
    try:
        identify_rc(np.empty((0, 1)), threshold=args.threshold, min_pixels=args.min_pixels)
        region_mask(np.empty((0, 1)), np.empty((0, 1)), extents=args.extent)
    except ValueError as exc:
        parser.error(str(exc))
    source = args.input.resolve()
    output = args.output.resolve()
    if source.is_file():
        if source.suffix.lower() not in HDF5_SUFFIXES:
            parser.error("输入文件后缀必须为 .hdf5 或 .h5（不区分大小写）")
        files = [source]
        root = source.parent
    elif source.is_dir():
        files = sorted(p for p in source.rglob("*")
                       if p.is_file() and p.suffix.lower() in HDF5_SUFFIXES)
        root = source
    else:
        parser.error(f"输入路径不存在：{source}")
    if not files:
        parser.error("输入目录中没有找到 .hdf5 或 .h5 文件")

    counts = dict(written=0, existing=0, empty=0, failed=0)
    for index, path in enumerate(files, start=1):
        relative = path.relative_to(root)
        # 保留完整源文件名和相对目录，避免同一时间的不同轨道/扩展名互相覆盖。
        destination = output / relative.parent / (relative.name + ".nc")
        try:
            status = process_file(path, destination, overwrite=args.overwrite, **options)
            counts[status] += 1
            LOGGER.info("[%s/%s] %s: %s", index, len(files), status, relative)
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            counts["failed"] += 1
            LOGGER.error("[%s/%s] failed: %s (%s)", index, len(files), relative, exc,
                         exc_info=args.verbose)
    LOGGER.info("完成：写入 %(written)s，已存在 %(existing)s，无区域交集/有效雨团 %(empty)s，失败 %(failed)s",
                counts)
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
