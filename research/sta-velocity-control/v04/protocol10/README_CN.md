# V04 protocol10 / series09：降落匹配修复后的条件授权批次

2026-09-26。用户“是”确认：先冻结并验证干净源码，再运行以下最多6次 Iris SITL。不是续跑旧五轮，不授权调参、补飞、额外冒烟、push、V05或实机。旧八批失败不改判。

顺序固定：9901 PID→ESTA X，9902 PID→ESTA X，9903 PID→ESTA X。启动失败亦计次；首个必需单轮或配对失败立即停止。新目录固定为 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/series09`，不得已存在。每轮重启、备份并逐字节恢复EEPROM，只清理自有仿真进程。

## 继承与唯一变化

完整参数/数值门槛/任务见 `v04_protocol10.load_protocol()`；执行文件只允许登记字段和landing10绑定变化。PID/ESTA参数文件与protocol09逐字节相同。实际 Iris10016 / quad_w / empty_grey.world；原项目 `./sitl/run.sh --headless --backend gazebo --model iris`，1倍速。原位置P、姿态、Y/Z速度PID和全部rate PID保持；rate MODE/AXES/DIV=0/0/1，RATT_TEST/TKO_MGT=0。

约2.5m高度，60–62s观察窗口包含32s零净X速度小激励；幅度0.2m/s，周期8s，加平滑包络，固定yaw。候选λ1=1、λ2=.2、ν限.4m/s²、纠偏限.8m/s²。唯一目标链Navigator→FMM→位置P/实验X激励；不增加setpoint发布者。安全/配对非劣门槛、日志覆盖、完整reset/primary及姿态双时间检查全部继承protocol09。

新入口flight12沿用离线flight11的降落钩子，并单独绑定protocol10授权。Checks继承已审计landing10监视器；环境授权/world绑定明确指向新协议。最终分析必须同时通过原完整分析链及landing10原始命令/状态/诊断复核，缺landing_context拒绝。旧入口不变，离线flight11仍禁用。

降落按原始diagnostic发布时间匹配过去或同刻vehicle_status，不混用异步CLI旧nav，也不借未来状态。未齐证据仅允许最长0.5s仿真/墙钟pending，不能当作通过；真实故障即时锁存。宿主降落轮询sleep=.1s不是控制器dt；原150s降落上限不变。完整结束仍要求落地、上锁、清除诊断及最终ULog验收。

种子只对IMU插件有效，其他传感器及宿主调度不保证独立，固定PID先行偏差保留。种子审计只排除本批execution/seed_audit及landing10提案/seed_audit这四个明确设计登记，真实job绝不排除；启动前再扫。295项资产及插件依赖固定。仅离线合成来源夹具可测试分析正例，不能变更历史飞行判定。

## 执行

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_protocol10.py --output <全新离线目录>
# 默认dry-run，不启动、不写参数/输出目录
python3 research/sta-velocity-control/scripts/run_v04_protocol10.py --source-head <完整冻结SHA> --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/series09'
# 仅完成干净提交复核及现场检查后追加：
# --execute --authorization <已记录本次用户确认的仓库外回执路径>
```

execution的flight_authorized=false不能单独启动；明确批准记录在外部回执，绑定stage、完整源码HEAD、execution SHA、最多6次及用户确认文字。回执不是签名、不是扩大授权。报告与实际结果另提交，失败不自动续飞。
