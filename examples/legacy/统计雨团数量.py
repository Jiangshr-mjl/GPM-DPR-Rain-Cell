import h5py
import numpy as np

rc = np.load('../data/DPR_rain_cell.npy', allow_pickle=True).item()

# 统计1天当中雨团数量
def oneday(rc):
    sum = 0
    for orb, rco in rc.items():
        print(orb, len(rco)-4)
        sum += len(rc[orb])-4
    print(sum)
    return


# 统计全年雨团数量
def oneyear(rc):
    sum = 0
    for day, rcd in rc.items():
        for orb, rco in rcd.items():
            sum += len(rco)-4
    print(sum)
    return sum


# oneyear(rc)

# for day, rc_d in rc.items():
#     y_sum = 0
#     print(day)
#     for orb, rc_h in rc_d.items():
#         print(orb, len(rc_h)-3)

# for i in range(1000):
#     print(f"{i}: {len(rc[str(i)]['row'])}")

# sum = 0
# for day, rc_d in rc.items():
#     for orb, rc_h in rc_d.items():
#         sum += len(rc_h)-3
#
# print(sum)

i = 0
for key, value in rc['216day']['2orb'].items():
    if i >= 4:
        print(f"{key}: {value['row'].shape[0]}")
    i += 1
