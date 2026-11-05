# R02：保护、交接、HTE 与日志离线接线

本目录属于 `research/sta-velocity-regularized`，以 R01 提交 `9d1c74fce9fa386e94e790514aeb8f2c718abc47` 为参考。
**R02 没有飞行预算，也不开放生产 MODE3。** 新内核现在被保护库链接，不能再沿用 R01“固件无新核符号”的证明；生产实例的私有准入开关恒为 false，真实模块测试另核查请求拒绝。测试友元只在测试翻译单元定义。

## 接口约定

- MODE0 原 PID、MODE1 原硬符号 ESTA；MODE2 保留拒绝，MODE3 为正则化显式 STA，本阶段仍拒绝生产生效。
- 新核离线夹具只准入 AXES1/3/4/7、DIV1。原 MODE1 的1…7路径保持。X/Y/Z 是本地 NED 北/东/下，不是机体系 roll/pitch/yaw。
- 三个 `MPC_VC_EPS_X/Y/Z` 默认 `.01/.01/.02 m/s`，工程域 `[.001,1]`，不夹紧无效参数。旧 ESTA 不使用 epsilon，修改该无关参数不改变其状态或配置代次。
- `s=v−v_sp`，`a_sta/nu` 为 m/s²；使用旧 nu 计算当前纠偏，再形成下一步候选。纠偏限幅→加一次原加速度 FF→原倾角/推力/Z优先映射→全选轴校验后提交。`a_proxy` 是推力映射代理，不是实际加速度测量。
- HTE、Z/XYZ/混合交接的反解必须使用相同分段 Psi。原 PID 与旧 ESTA 表达式和操作顺序保留。受保护的 nu 不冒称无约束理想递推。
- `sta_velocity_ctrl_status` 布局不变；扩展 `velocity_ctrl_selection` 的 variant、请求/实际 epsilon、配置代次、暂存/拒绝，按 `publish_seq + timestamp_sample` 精确关联，不近邻猜配、不去重。

## 离线验证入口

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 research/sta-velocity-control/regularized_sta/r02/verification/verify.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R02/全新目录名'
```

验证器设置项目依赖环境；外部输出目录必须不存在。它运行适用历史测试链、新模块/参数/保护/逐样本对照、工具负例，构建 SITL/Gazebo（`DONT_RUN=1`）；保存真实命令、退出码、XML、去重计数、输入/输出指纹。不会启动仿真、修改真实 EEPROM 或注册种子。
旧 V08 源码不变资格与 AX04 冻结源码资格不适用于本次新实现，明确列为未执行/不适用，不能计作通过；历史功能回归仍执行。

冻结参考见 [reference](reference/README_CN.md)，工具入口见 `tools/run.py`。工具默认只打印配置，`--execute` 在此版本硬拒绝，即使传入 manifest/authorization 字符串也不能打开飞行。

## 进入 R03 前

R02 完整结果以 [R02 报告](../../reports/R02.md) 为准，不凭某一次构建成功验收。下一阶段还必须逐门冻结准确的任务、数值门槛、参数/epsilon、唯一目标源、种子、预算、源码/固件/模型/分析器指纹；完成模块准入和完整新日志链接线后才能在干净提交上飞行。
旧日志只读回放、新模式合成反例和实际 Run/uORB 夹具不是 MODE3 的真实飞行证据。R03 A/B/C/D 每门9次，首败停批，不补飞凑通过；用户已给阶段连续授权，但没有取消预算与证据要求。
