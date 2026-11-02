# SuperTwisting2.0 简易悬停对比结果

原版完整复现已构建并完成 Iris SITL；与现有 RSTA、RISTA 各完成一轮约 2.5 m 起飞、10 s 稳定悬停、降落上锁。未改作者控制律或增益，未调 RSTA/RISTA 参数，未实机、未提交或 push。

|系统|X 速度 RMS|Y 速度 RMS|Z 速度 RMS|水平位移 RMS|高度偏差 RMS|
|---|---:|---:|---:|---:|---:|
|原版 STA2|0.071641|0.015714|0.019117|0.080777|0.027845|
|RSTA|0.015924|0.015470|0.035504|0.019505|0.040454|
|RISTA|0.013713|0.015843|0.020555|0.020188|0.023557|

速度单位 m/s，位移/高度单位 m；使用各自完整 10 s 悬停窗、按时间加权。速度 RMS 相对零速度，不是内部目标跟踪 RMSE。三组各 n=1，只描述这一次完整系统表现，不能证明算法的一般优劣。

原版 `fc3720f67767c78cfab668777de13f68562fe2fd` 的三轴角速度为作者 STA；XY 速度是归一化误差 PID，Z 速度 STA 输出被注释。现有 RSTA/RISTA 是 XYZ 速度替换、角速度 PID，主仓库 HEAD 为 `8079e17177e3edb597d8da1597081a82cbd6747a` 加现场已有改动。两套 PX4 与接触模型不同；原生位置日志分别为 125/10/10 Hz，不能拿曲线平滑程度比较高频抖振。

## 执行记录

- 原固件构建退出码 0；Gazebo 插件构建退出码 0。最初缺 GStreamer 开发文件导致构建退出码 2，补齐私有依赖后成功；未修改系统安装或作者算法。
- 49 项脚本/分析离线测试通过，退出码 0；不将其冒称作者控制核单元测试。
- S001、S102 在解锁前因工具兼容问题退出 1：姿态话题首发等待、合法诊断 NaN 的 JSON 保存。两次失败原样保留。相应修订仅在地面工具，安全数值规则未变。
- 最终 S101/S202/S203 飞行与原生日志验收均退出 0。5 次启动、3 次起飞、3 次接受，无已起飞任务重试、无调参。
- 独立分析重跑核对指标；文件与 ULog SHA-256、未解锁证据、参数精确恢复、原有 99 个文件保护检查见 `verification.json`。
- 附加高频镜像话题探查未找到 `vehicle_local_position_log`，该只读探查退出 1。没有用插值或其他实验日志补齐；最终图使用真实的原生话题采样率。

## 文件

- [图表及简明中文说明](/home/yr/Documents/UPSTREAM_STA2_RSTA_RISTA_HOVER_20261102/README_CN.md)
- [完整核对记录](/home/yr/Documents/UPSTREAM_STA2_RSTA_RISTA_HOVER_20261102/verification.json)
- [最终任务清单](</home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-HOVER-20261102/manifest03.json>)
- [复现与启动方法](README_CN.md)

原版在 `/home/yr/Desktop/Codev-SuperTwisting2-original` 独立运行；主仓库分支 `research/upstream-supertwisting2` 仅新增复现/比较工具，没有用作者代码覆盖现有速度控制研究。
