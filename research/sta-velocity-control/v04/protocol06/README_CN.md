# V04 protocol06 / series05：新授权六次批次

用户在 handoff06 离线修订后明确要求“重新冻结并授权新批次”。起点 `5beaecfd7376178259b547e0f4d1d79156aab70a`，研究分支 `research/sta-velocity-control`。本文件不是飞行通过报告。

## 清单与边界

| 顺序 | 种子 | 速度 MODE / AXES |
|---|---:|---|
| run01 | 9501 | PID 0/0 |
| run02 | 9501 | ESTA X 1/1 |
| run03 | 9502 | PID 0/0 |
| run04 | 9502 | ESTA X 1/1 |
| run05 | 9503 | PID 0/0 |
| run06 | 9503 | ESTA X 1/1 |

最多六次，启动失败也消耗尝试；每轮及配对任一必需门槛失败立即停止，不补飞、不增加调参、不得续用旧五轮。只有全部六轮和三个配对通过才可验收V04。仅IMU显式播种；其他随机源及宿主调度并非独立，固定PID先行的顺序偏差继续披露。

原位置P、Y/Z速度PID、姿态和全部rate PID不变，rate模式/轴/分频为0/0/1，旧rate激励/起飞管理关闭。唯一ESTA候选λ1=1、λ2=.2、ν限.4m/s²、纠偏限.8m/s²；原FF和HTE保留。禁止XY/XYZ扩展、ISTA、实机、push和V05。

## 继承与唯一任务修订

`v04_protocol06.load_protocol()`固定继承05数值规则，并以SHA锁定05执行配置与handoff06离线契约。旧协议不修改。原目标高度2.5m、连续3秒入口、12秒激励等待、32秒X正弦和60秒观察、起降、reset分类、安全/性能/日志门槛均不变。

目标交接使用已验证handoff06：正常首次磁对齐、POSCTL稳定1秒并一次固定yaw后，从原始机载trajectory采集原XY保持目标，以原NED参考反投影成COMMAND_INT整数经纬度，发送一次明确XY/高度/yaw；不要求POSCTL已清空的Navigator目标有效，不改用实际位置或真值。编码误差≤.02m，3秒入口/观察的下游XY目标偏差≤.05m。5秒内同时核对新鲜ACK、AUTO_LOITER和目标，准入前异步pending、准入后目标丢失即失败；不重发、不延长150秒准备期。

原始运行根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series05`，必须不存在才能启动。保存源/固件/模型/插件/参数/命令/ULog指纹及ledger，逐轮完整恢复原EEPROM。控制参数分别在pid/esta/frozen.json，185项执行资产在frozen.json；种子审计只排除本协议注册文件，不排除真实实验。

## 执行

先明确范围提交，再在该干净提交重建并通过非零测试；核对所有资产、子模块、固件source SHA、种子、进程、端口及参数。入口默认dry-run，实际执行须指定精确授权令牌和冻结输出目录。旧 `run_v04_flight06.py` 仍禁止飞行；新授权入口绑定 `run_v04_flight07.py` 和独立06分析器。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_protocol04.py --output <全新验证目录>
python3 research/sta-velocity-control/scripts/run_v04_protocol06.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04/series05' \
  --source-head <本协议提交完整SHA>
# 仅执行本次已授权批次时，在上一命令附加：
# --execute --authorization V04-protocol06-series05-six-attempts
```

沿用`./sitl/run.sh --headless --backend gazebo --model iris`，Iris10016/quad_w、empty_grey.world、1倍速，不是DP1000。失败后不得换新目录或令牌私自重跑。

## 离线结果

提交前protocol06_verify01：109个不同C++、180个Python（新增8项），SITL及DONT_RUN Gazebo构建退出0；旧失败日志预期拒绝退出1，不改判历史。新增测试包括继承规则、仅目标接口变化、授权/错误绑定零副作用、六轮三对预算与失败停止/参数恢复、新分析器完整合成链。没有新增控制数学或生产源码。真实飞行结果另存报告，不将离线通过称作飞行通过。
