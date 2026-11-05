# RI00 离线来源审计包

[阶段报告](../../reports/RI00.md) · [公式与接口冻结](MATH_INTERFACE_CN.md) · [执行前探针规格](PROBE_SPEC_CN.md) · [实测摘要](results/summary.json)

本目录不在 PX4 CMake 生产构建链。source_bridge.cpp 只把原上传 C++ 头文件和当前 selector 暴露给离线 Python；不在此实现新生产控制律。

## 复现

需要原上传包、当前 R03 基线、既有生成消息、R03 revision11 冻结资产及 D/run029 原始 ULog。probe.py 刻意要求入口 HEAD=a286e40ec8bfbb0500b1c24add18c1a98b908778；RI00 提交后的 HEAD 不再符合入口。复现应使用该基线的独立检出并只复制本 RI00 探针文件，或在下一阶段另冻入口校验，**不要回退/清理当前用户工作区**。本说明不自动创建检出或运行实验。

本次实际命令（原目录已存在，不得覆盖）：

~~~bash
cd /home/yr/Desktop/Codev-autopilot
PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python" \
python3 -B research/sta-velocity-control/regularized_ista/ri00/probe.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261023/RI00/audit02'
~~~

再次复现必须选未存在的新离线输出目录；没有飞行入口、参数加载、种子登记或网络操作。原包 CMake 构建和薄桥编译也只写该外部目录。

archive.py 生成小证据镜像及全外部工件索引，不覆盖已存在目录。实际归档命令：

~~~bash
python3 -B research/sta-velocity-control/regularized_ista/ri00/archive.py \
  --audit '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261023/RI00/audit02' \
  --previous-audit '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261023/RI00/audit01' \
  --output research/sta-velocity-control/regularized_ista/ri00/results
~~~

## 证据边界

- results/entry.json：真实 HEAD、工作区和33递归子模块。
- source_fingerprints/models.json：原文件指纹及 SLX 静态内容核对，不是 Simulink 仿真。
- command_01…11.json/log、probe_tests.log：真实命令/退出码及12项测试。
- grid.json：4896单步float/double核对；不是4896独立实验。
- cadence.json：原 ULog 指纹及6399个连续实测间隔；只读解码，不改判旧日志。
- closed_loops.json：90条60秒离线对象，含6条预先指定的不可行限幅反例；不能称90次飞行或全部跟踪成功。
- interface/source_limitations.json：当前全链指纹、完整127项来源参数、MODE4仍拒绝、源包弱提交/数值限制。
- archive.json：两次离线运行全部外部文件的路径/长度/SHA、环境、冻结资产复核和探针源码身份。audit01完整保留，audit02补4项测试并修正过宽的结果标签；最终引用audit02，不累加样本数。

保存的7980行 MATLAB fixture 由本次 C++ 测试读取；本机没有发现 MATLAB/Octave 可执行文件，未重跑 MATLAB。未构建新 PX4、未重跑整套生产控制器回归、未启动 Gazebo、未接执行器。
