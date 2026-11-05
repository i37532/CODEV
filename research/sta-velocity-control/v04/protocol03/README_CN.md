# V04 protocol03：明确高度任务与计划降落分类

本协议承接 protocol02 设计；用户已批准新六次上限任务及正常降落 Gate=2 的最小日志修订。旧协议和失败不覆盖。此文件不是飞行通过证明。

## 固定范围

- Iris Gazebo Classic，原项目启动器；仅速度 X PID/ESTA 对比，其余速度轴、姿态、角速度保留 PID/原控制。
- λ1=1、λ2=0.2、ν限0.4 m/s²、纠偏限0.8 m/s²；不搜索、不改模型或起飞逻辑。
- 9201 PID→ESTA、9202 PID→ESTA、9203 PID→ESTA，最多6次。每对通过才进入下一对；启动失败也计次，任何必需失败停止，无补飞。
- 固定顺序存在顺序偏差；仅 IMU 创新支持显式配对种子，不宣称所有随机源独立。

## 任务与日志修订

保持原起飞；完成后仅发一次 DO_REPOSITION，明确导航高度为冻结地面估计以上2.5m。X/Y沿用导航目标，yaw为起飞前heading。本仓库param4实际按弧度消费，不可直接移植为其他飞控通用命令。
核实新ACK、实际AUTO_LOITER、导航/轨迹/消费目标；连续3s高度2–3m且|vz|<0.2，gate+10s内完成入口，之后60s观察。12s等待、32s速度波形和所有旧数值阈值不变。在线CLI有4/6位小数精度，离线坐标比较分别使用记录精度及同源ULog原值，绝不插值补样。

仅在完整波形及观察完成、唯一计划land命令成功、实际AUTO_LAND后，单独Gate=2且激励输出零分类为预期结束。保留原始位，不改成零；早退、回到LOITER、Clock/Controller位及组合仍失败。disarm必须清零。first_fail/retry_result非零始终拒绝，first_input按有效输入通道逐位核对。

新入口独立于历史脚本；生产唯一变动为高频日志配置增加command_ack及navigator triplet注册，保留原SDLOG_PROFILE位。没有修改控制律、默认参数、Takeoff、导航或估计器。

## 执行方式

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
# 默认仅打印清单。执行必须使用核实的完整源码SHA；目录存在即拒绝，不能重用。
python3 research/sta-velocity-control/scripts/run_v04_protocol03.py \
  --source-head <完整源码提交SHA> \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series02'
# 源码提交、干净重建与全部离线检查通过后，才为同一命令添加 --execute。
```

准确参数/阈值/授权/缺失处理见 protocol.json；资产快照 frozen.json，PID/ESTA各自完整参数在子目录。执行时再次检查分支、提交、递归子模块、资产/插件、固件版本、种子历史、端口、空间及全量参数备份。控制流程和模拟故障测试不等于实际飞行接受；最终结论见报告。
