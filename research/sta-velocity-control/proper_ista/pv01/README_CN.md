# PV01 独立 Proper-ISTA 速度核

仅离线核/数值回归与SITL编译。**不能切换MODE5起飞**，没有保护适配器或执行器路径。旧PID/R-STA/R-ISTA不变。

- [有限协议](PROTOCOL_CN.md)
- [数学/数值/事务契约](NUMERICS_CN.md)
- [阶段报告](../../reports/PV01.md)
- [紧凑结果](results/summary.json)、[命令/测试/失败证据](results/evidence.json)、[外部档案指纹](results/archive_index.json)

## 复现命令

在仓库根运行，工具默认dry-run；实际执行必须指定**全新**外部目录。没有一条命令会启动Gazebo或飞行。

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 research/sta-velocity-control/proper_ista/pv01/verify.py
python3 research/sta-velocity-control/proper_ista/pv01/build_verify.py

# 重算同一固定诊断矩阵，不增加独立科学样本
python3 research/sta-velocity-control/proper_ista/pv01/verify.py --execute \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-PROPER-20261028/PV01/new-model-run'

# 新Python参考/负例测试
python3 -B research/sta-velocity-control/proper_ista/pv01/test_verifier.py -v

# 项目测试构建；依赖项目已有本地Python库
export PYTHONPATH="$PWD/.px4-python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
make tests TESTFILTER=ProperIstaVelocityControl -j4
make px4_sitl_default -j4
```

`build_verify.py`是本阶段封存验收脚本：严格核对入口HEAD `39f1e9bc006655e6240f633310c6c44cb64a8266`、四个源码路径和49目标，最终提交后直接执行会因HEAD不同安全拒绝；不要为复现而reset工作区。后续阶段应另建自己的资格收据，或在保留已知改动的独立离线环境重建本次来源。其构建命令/49目标清单/每个二进制指纹均保存在evidence中。

`entry.py`归档旧固件/身份；`closeout.py`执行67个Python用例、重算52对象并独立回放指标、检查用户文件和既有实现指纹；`export.py`保存小摘要与外部索引。后两者默认本次证据路径，是阶段取证工具，不是通用飞行入口。

52条36秒轨迹包含4个预先定义的控制能力不足限幅反例；全部完成不等于全部成功跟踪。4旧停止各4096步是固定停止点h的局部生命周期，完整交替周期另见对象矩阵。MATLAB未运行，未进行新飞行/实机或调参；支持的数值环境暂限x86 SSE最近舍入、渐进下溢。
