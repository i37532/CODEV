# RI01 冻结参考：RI02 逐样本防退化

唯一来源提交：`2f19cefc850ef4b77a8bcdc455aaec193f3da331`。13 个文件全部经 `git show` 读取，不读取正在修改的工作区；`manifest.json` 固定原始与机械转换后的 SHA-256。`freeze.py` 默认只读重核，`--write` 仅首次生成且拒绝覆盖。

冻结 PositionControl、ControlMath、StaVelocityProtection、StaVelocityControl、RegularizedStaVelocityControl 的头/实现，以及 selector、decimation、host clock 三头。所有重命名只按完整标识符增加 RI01 前缀，包括头文件名、class、namespace 和 host clock；逆转换必须逐字节还原原提交。无控制数学、状态顺序或限幅改动；旧 R01/AX00/V00 快照不覆盖。

`RegularizedIstaRegressionTest` 的24个确定性配置序列：

- PID/AXES0：固定10ms与交替8/12ms，各2048步。
- R-STA/AXES1、3、4、7：每掩码相同两组，各2048步。
- 旧ESTA/AXES1…7：每掩码相同两组，各2048步，仅离线兼容，不进入新的统计组。

合计49152对主样本，另384对同sample重算；仅24个gtest用例，不能把高频样本冒充独立实验。有限float与正负零按位相同，NaN比较无效使能语义而不限定payload。比较实际发布加速度/推力/姿态、积分/纠偏、nu与保护状态、选择/配置代次、更新序列、HTE及约束。宿主执行耗时不是确定性数学状态，不要求逐位相同。

输入覆盖XYZ、非零速度与加速度FF、位置P+速度FF、纯加速度/XY成对NaN、半组NaN负例、无效测量恢复、约束、原PID gain更新、armed暂存/取消和disarm修改、地面/ramp/接触/弹跳、Z及XYZ seed、HTE、重置及同sample二次update。ramp在这里指模块给PositionControl的阶段/速度限值输入，真实Takeoff类、模块uORB与参数持久化另由本阶段测试目标执行，不冒称这个参考包含整个模块。

此处保留全部原算法路径，并非独立算法数学证明，也不证明新R-ISTA保护/飞行安全；新算法负例和对象另行验证。当前uORB消息布局、matrix/math/platform库为共享基础依赖；上述13份控制源码则不依赖新生产保护核。

只读复核：

```bash
python3 -B research/sta-velocity-control/regularized_ista/ri02/reference/freeze.py
```

实际测试数、运行命令、退出码、失败和XML证据由RI02报告记录；此说明不预填运行通过。
