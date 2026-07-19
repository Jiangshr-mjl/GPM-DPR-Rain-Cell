"""
批量识别雨团：
    1.一个轨道一个 nc文件
    2.可进一步优化点：文件名以时间命名
"""
import os
import h5py
import numpy as np
import xarray as xr
from RCprocess import RCidentify as rcp

for year in range(2015, 2016):

    path = '/d0/data/GPM/GPM_2ADPR.07/'  # 数据主干路径
    print(f'Year:{year}')
    year_path = path + str(year) + '/'  # 年路径
    # 获取年路径下所有天文件夹
    days = [f for f in os.listdir(year_path) if os.path.isdir(os.path.join(year_path, f))]

    counts = 0  # 计数器
    for day in days:
        counts += 1
        print(f'处理目录{counts}：Day{day}')

        day_path = str(year_path + '/' + day)  # 数据-天
        # 判断目录是否存在，存在则跳过循环
        if os.path.exists(day_path):
            continue

        # 创建储存路径到day
        os.makedirs('/d1/jiangshr/DATA/rc_data/' + str(year) + '/' + str(day))

        orb_id = 0  # 轨道编号
        for file in os.listdir(day_path):
            # 如果非HDF5文件，则跳过
            if not file.endswith('.HDF5'):
                continue

            try:
                f = h5py.File(day_path + '/' + file)  # 打开HDF5数据
            except (KeyError, OSError) as e:
                print(f'异常文件：{file}')
                print(f'报错类型：{type(e)}')
                print(f'报错信息：{e}')
                continue

            # 读取数据
            try:
                # 二维
                lat = f['FS/Latitude'][:]  # 纬度
                lon = f['FS/Longitude'][:]  # 经度
                pr_s = f['FS/SLV/precipRateNearSurface'][:]  # 地表降水
                hst = f['FS/PRE/heightStormTop'][:]  # 风暴顶高度
                typePrecip = f['FS/CSF/typePrecip'][:]  # 降水类型
                # 三维
                pr_3d = f['FS/SLV/precipRate'][:]  # 三维降雨率
                R = f['FS/SLV/zFactorFinal'][:]  # 三维反射率
                dsd = f['FS/SLV/paramDSD'][:]  # 粒子常数（包括粒子浓度和粒子平均直径）
            except (KeyError, OSError) as e:
                print(f'异常文件：{file}')
                print(f'报错类型：{type(e)}')
                print(f'报错信息：{e}')
                continue

            # 获取区域掩码
            mask = rcp.region_mask(lat, lon)

            if np.any(mask):  # 如果扫描路径经过研究区域

                # ==============================获取时间===============================
                time = rcp.connect_time(f)
                time = time[mask][0]

                # ============================获取雨团识别点============================
                # 提取出研究区域地表降水
                pr_s = pr_s[mask]
                # 初始化雨团id编码
                rcid = np.zeros_like(pr_s)
                # 处理误差值（认为小于0.5mm/h的都是缺测值）
                pr_s[pr_s < 0.5] = np.nan
                # 识别雨团
                rcid = rcp.identify_rc(pr_s, rcid)
                if np.max(rcid) == 0:
                    continue
                else:
                    rcid[rcid == 0] = np.nan

                # ==============================创建nc文件=============================
                # 读取掩码区域数据
                lat = lat[mask]
                lon = lon[mask]
                hst = hst[mask]
                pr_3d = pr_3d[mask, :]
                R = R[mask, :, :]
                dsd = dsd[mask, :, :]
                typePrecip = typePrecip[mask]
                # 设置coordinate
                nscan = np.arange(0, lat.shape[0], 1)
                nray = np.arange(0, 49, 1)
                nbin = np.arange(0, 176, 1)
                # 编辑dataset
                ds = xr.Dataset(
                    {
                        'time': time,
                        'lat': (['nscan', 'nray'], lat),
                        'lon': (['nscan', 'nray'], lon),
                        'rcid': (['nscan', 'nray'], rcid),
                        'prs': (['nscan', 'nray'], pr_s),
                        'pr3d': (['nscan', 'nray', 'nbin'], pr_3d),
                        'hst': (['nscan', 'nray'], hst),
                        'R': (['nscan', 'nray', 'nbin', 'nfreq'], R),
                        'dsd': (['nscan', 'nray', 'nbin', 'nDSD'], dsd),
                        'typePrecip': (['nscan', 'nray'], typePrecip)
                    },
                    coords={
                        'nscan': nscan,
                        'nray': nray,
                        'nbin': nbin,
                        'nDSD': np.array([0, 1]),
                        'nfreq': np.array([0, 1])
                            }
                )
                # 储存为nc文件
                ds.to_netcdf(f'/d1/jiangshr/DATA/rc_data/{str(year)}/{str(day)}/orbit{orb_id}_{str(time)}.nc')
                orb_id += 1
