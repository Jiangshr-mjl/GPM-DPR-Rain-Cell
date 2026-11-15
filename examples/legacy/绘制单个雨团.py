import numpy as np
from 备份代码 import RC_processing as rcp

# ===================================读取数据====================================

# 读取雨团
rain_cell = np.load('DPR_rain_cell.npy', allow_pickle=True).item()
# allow_pickle=Ture 表示允许读取python文件
# .item() 表示读取为python对象

# ===================================绘制图像====================================
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors


# 获取范围函数
def get_extents(lat, lon, wide):
    """
    获取雨团展示范围
    :param lat: 纬度
    :param lon: 经度
    :param wide: 跨度
    :return:
    """
    mlat = int(np.mean(lat)) + 0.5
    mlon = int(np.mean(lon)) + 0.5
    wide = wide / 2
    return [mlon - wide, mlon + wide, mlat - wide, mlat + wide]


# 绘制单个雨团
def plot_single_rc(rain_cell, day, orb, id, wide=3, s=50, save=False, path='./'):
    """
    :param rain_cell: <dict> 雨团数据集
    :param day: <str> 数据集索引 天
    :param orb: <str> 数据集索引 轨道
    :param id: <int>or<str> 雨团编号
    :param save: <bool> 判断是否保存为图像
    :param path: <str> 保存路径
    :return:
    """
    # 读取数据
    dlat, dlon, dpr, lat, lon, pr = rcp.read_rc(rain_cell, day=day, orb=orb, id=str(id))

    # 获取范围
    extents = get_extents(lat, lon, wide=wide)

    # 设置字体
    plt.rc('font', family='Times New Roman')

    # 设置调色板参数
    bins = [0, 0.2, 0.4, 1.0, 2.0, 3.0, 8.0, 16.0, 40.0]
    nbin = len(bins) - 1
    cmap = cm.get_cmap('jet', nbin)
    norm = mcolors.BoundaryNorm(bins, nbin)

    # 创建画布
    fig = plt.figure(figsize=([11, 9]))
    ax = fig.add_subplot(projection=ccrs.PlateCarree())

    # 地理环境
    ax.set_extent(extents)  # 设置范围
    ax.coastlines()
    ax.add_feature(cfeature.LAND.with_scale('10m'), facecolor='lightgray')

    # 绘制扫描轨道
    ax.plot(dlon[:, 0], dlat[:, 0], color='black', transform=ccrs.PlateCarree())
    ax.plot(dlon[:, -1], dlat[:, -1], color='black', transform=ccrs.PlateCarree())

    # 绘制雨团
    sc = ax.scatter(lon, lat, c=pr, cmap=cmap, norm=norm, s=s, transform=ccrs.PlateCarree())

    # 设置标签
    xticks = np.arange(int(extents[0]), int(extents[1])+1, 1)
    yticks = np.arange(int(extents[2]), int(extents[3])+1, 1)
    xticks_labels = [f"{x}°E" for x in xticks]  # 添加经度信息
    yticks_labels = [f"{y}°N" for y in yticks]  # 添加纬度信息
    plt.xticks(xticks, xticks_labels, fontsize=21)
    plt.yticks(yticks, yticks_labels, fontsize=21)

    # 绘制颜色棒
    cbar = plt.colorbar(sc, ax=ax, orientation='vertical')
    cbar.ax.tick_params(labelsize=17)  # 设置刻度标签的字体大小
    cbar.set_label('(mm/h)', fontsize=20)  # 设置颜色条标签

    if save:
        plt.savefig(path + f'single_rc_{day}_{orb}_{id}.png', format='png', dpi=600)
    else:
        plt.show()

    return


plot_single_rc(rain_cell, day='296day', orb='1orb', id=10, wide=5, s=18, save=True, path='D:/1_TDRC/figure/rc_identify/')
