import numpy as np
import matplotlib.pyplot as plt


# 绘制降水总图
def plot_pr(fig, g, pr, lon, lat):
    # 设置调色板参数
    bins = [0, 0.2, 0.4, 1.0, 2.0, 3.0, 8.0, 16.0, 40.0]
    nbin = len(bins) - 1
    cmap = cm.get_cmap('jet', nbin)
    norm = mcolors.BoundaryNorm(bins, nbin)

    # 设置axes对象
    ax = fig.add_subplot(g, projection=ccrs.PlateCarree())

    # 地理环境
    extents = [111, 116, 19, 24]
    ax.set_extent(extents)  # 设置范围
    ax.coastlines()
    ax.add_feature(cfeature.LAND.with_scale('10m'), facecolor='lightgray')

    # 绘制扫描轨道
    ax.plot(lon[:, 0], lat[:, 0], color='black', transform=ccrs.PlateCarree())
    ax.plot(lon[:, -1], lat[:, -1], color='black', transform=ccrs.PlateCarree())

    # 绘制雨团
    sc = ax.scatter(lon, lat, c=pr, cmap=cmap, norm=norm, s=1.8, transform=ccrs.PlateCarree())

    # 设置标签
    xticks = np.arange(int(extents[0]), int(extents[1]) + 1, 1)
    yticks = np.arange(int(extents[2]), int(extents[3]) + 1, 1)
    xticks_labels = [f"{x}°E" for x in xticks]  # 添加经度信息
    yticks_labels = [f"{y}°N" for y in yticks]  # 添加纬度信息
    plt.xticks(xticks, xticks_labels, fontsize=21)
    plt.yticks(yticks, yticks_labels, fontsize=21)

    # 绘制颜色棒
    cbar = plt.colorbar(sc, ax=ax, orientation='vertical')
    cbar.ax.tick_params(labelsize=17)  # 设置刻度标签的字体大小
    cbar.set_label('(mm/h)', fontsize=20)  # 设置颜色条标签

    return


def plot_rc(fig, g, rc, dlat, dlon):
    # 设置axes对象
    ax = fig.add_subplot(g, projection=ccrs.PlateCarree())

    # 地理环境
    extents = [111, 116, 19, 24]
    ax.set_extent(extents)  # 设置范围
    ax.coastlines()
    ax.add_feature(cfeature.LAND.with_scale('10m'), facecolor='lightgray')

    # 绘制扫描轨道
    ax.plot(dlon[:, 0], dlat[:, 0], color='black', transform=ccrs.PlateCarree())
    ax.plot(dlon[:, -1], dlat[:, -1], color='black', transform=ccrs.PlateCarree())

    # 绘制雨团
    for rci in range(len(rc)-4):
        row = rc[str(rci)]['row']
        col = rc[str(rci)]['col']
        lon = dlon[row, col]
        lat = dlat[row, col]
        ax.scatter(lon, lat, s=2, transform=ccrs.PlateCarree())

    # 设置标签
    xticks = np.arange(int(extents[0]), int(extents[1]) + 1, 1)
    yticks = np.arange(int(extents[2]), int(extents[3]) + 1, 1)
    xticks_labels = [f"{x}°E" for x in xticks]  # 添加经度信息
    yticks_labels = [f"{y}°N" for y in yticks]  # 添加纬度信息
    plt.xticks(xticks, xticks_labels, fontsize=21)
    plt.yticks(yticks, yticks_labels, fontsize=21)

    return
