# V00 恢复批次02：实际 world 核验修复与三次新尝试

2026-09-21，用户明确同意修复 world 核验、补齐工具测试，重新冻结并执行三轮基线。
起点22bf39a3b1361bf032923817bb1b37496e448297；research/sta-velocity-control。
旧批次01的1次启动失败、0次起飞、后2次未运行及所有原始数据原样保留。
本批次是另行授权的最多3次新尝试，不将旧失败剔除或计为通过。

## 改动与冻结

只改运行器的world证据核验，新增独立验证工具及9个离线测试。不改控制律、Takeoff生产逻辑、
控制增益、模型、插件或日志调度；批次01的测试修订和3个高频话题请求保持。
运行时读取本次launcher的session ID、gzserver实际argv和白名单环境变量，保存world_process.json。
要求系统恰有一个gzserver，属于本次session；实际argv为冻结world绝对路径，环境world/master一致，文件SHA一致。
不再要求console打印world；仍独立核对Iris模型的Using路径。错误、缺失、多实例或不属于本次启动均拒绝。
环境仅留PX4_SITL_WORLD和GAZEBO_MASTER_URI，不归档其他进程环境。

测试包括：正确world但不依赖console、错误argv即便环境正确、无实例/多实例、其他session、
非session leader、缺失/相对/多world路径、环境或master错误、错误进程名、真实/proc读取（不启动模拟器）。
verification04：37个不同C++用例、25个Python用例全部通过，verify及子命令退出0。
Position15、ControlMath9、Takeoff8、Rate1、Dispatcher4；重复构建阶段测试不累计数量。

## 准确运行协议

继承[批次01详细协议](../resume01/PROTOCOL_CN.md)的全部任务、安全/数据阈值和参数恢复规则，
完整机器可读副本为本目录protocol.json，参数/资产为frozen.json。
唯一变化为world核验证据方式和新授权批次，不放宽任何飞行、日志或指标门槛。
顺序run01→run02→run03；最多3次；任一必需检查失败立即停止，禁止补飞、自动重试或执行余下尝试。
每轮新进程、1倍Iris Gazebo SITL，预热≥30s，起飞2.5m，稳定3s，悬停60s，降落并上锁。
种子均null，原默认随机引擎；不得声称3个独立种子。
目标唯一来源是原机载flight_mode_manager链；只发送commander命令、中性RC和GCS心跳。
原位置P、XYZ速度PID、姿态与rate PID，MODE=0、AXES=0、DIV=1、RATT_TEST=0、TKO_MGT=0。
SDLOG_PROFILE保留原位并OR16、SDLOG_DIRS_MAX=1000；不删除旧日志，逐次停机后完整恢复原EEPROM字节。
Iris10016/quad_w/empty_grey不是DP1000配置，不部署实机、不启动旧ISTA、不执行V01、不push。

先审查并提交本协议/源码，在干净提交上重新构建SITL/Gazebo目标（DONT_RUN=1），
将完整SHA传给运行器；实际固件SHA写ledger，启动器导致固件变化即拒绝。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
DONT_RUN=1 make px4_sitl_default gazebo_iris -j4
python3 research/sta-velocity-control/scripts/run_v00.py --execute \
  --source-head '<本批次协议完整提交SHA>' \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V00/series02'
```

不带--execute仅dry-run；已有输出目录拒绝覆盖。首次失败或全部完成后另作结果提交，
报告实际命令、退出码、尝试/完成/接受数、日志SHA及未执行项，更新外部实时进度。
