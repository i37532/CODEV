# RI01 独立数值参考、fixture 与对象

先阅读 [执行前规范](SPEC_CN.md)。这里只编译新增纯核的共享库，在独立 ZOH/两级滞后对象中计算；没有 Gazebo、PX4 启动或参数写入入口。

本轮实际执行结果见 [RESULTS_CN.md](RESULTS_CN.md)，注意84条完整60s与18条数值域停止的区别。

从仓库根执行，必须选择尚不存在的外部输出目录：

~~~bash
python3 -B research/sta-velocity-control/regularized_ista/ri01/model/check.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI01/model_attemptNN'
~~~

脚本需要 Python3 标准库与 g++，不需要 MATLAB、NumPy 或 SciPy。输出有编译命令/退出码、6项独立参考自身单测、单步网格、已保存 MATLAB CSV 核对、102条对象轨迹和文件指纹。已有目录拒绝覆盖；失败写 failure.json。重复运行不增加独立科学样本。

check.py 的 oracle 采用单调二分求根，不复制 C++ 解析式。kernel_bridge.cpp 只转发新内核并保存其候选给独立 commit，不实现数学公式、不注册模块。所有实际核状态为 float，独立对象和参考为 binary64；对象分别持有状态，非对实际轨迹作事后同式回算。

来源 CSV 的算法1才是此次 R-ISTA，算法0保留但不计作新核验证。CSV 是原已保存数据，本工具没有重跑 MATLAB。来源 lo/hi/nu_max 包装用于离线追溯，不进入 PX4 生产保护；核输出只含纠偏，FF 在对象/离线包装中单独加一次。

理想固定周期、实际变周期、测量噪声、滞后、受限结果分列。不可行限幅反例不是跟踪成功；极小量进入严格数值域拒绝的轨迹保留实际停止点，不宣称完成60秒。全部结果只说明列明离线对象，不证明真实飞行稳定、R-ISTA优于其他算法或理论全局收敛。
