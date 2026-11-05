# V04 protocol15：两组通过，第三组因任务外导航消息歧义停止

2026-09-26。**本批 failed/needs_revision；V04 尚未完成同一新批次三组配对。** 计划6轮，实际5轮完整起降，前4轮接受、2组配对通过；15003 PID最终日志拒绝，第6轮未启动。历史失败不追认，不续用剩余预算，不push、不实机、不进入V05。Z仍仅有离线原型，未接执行器。

## 本批事实与结果

协议/源码 `99a832ae109a850a0ba64b4daa26c3c45efee545`，分支research/sta-velocity-control；飞前工作区及递归子模块干净。395项资产，执行SHA `db192d49df8c0601ee78d17b78c501a78fac951aaa858177cd5f1c4eebfd0095`，固件SHA `d4df6f753b21d5ed36fc13292220bae1fcc2e179a045bce79bad91f2eb4d3b52`。干净提交实际140项不同C++、373Python及SITL/Gazebo构建通过，退出0。

使用项目Iris启动器、原模型/world、唯一flight_mode_manager目标发布者。原位置P、Y/Z速度PID、姿态和全部rate PID不变；ESTA仅本地NED X。候选lambda1=1、lambda2=0.2、nu限0.4、加速度纠偏限0.8；共同下降参数0.6/0.55、日志profile1171，与protocol13/14相同。三秒原始入口、约2.5m、60秒观察/32秒小激励、固定yaw、原安全/性能/日志门槛均飞前固定。

| 运行 / 种子 | 控制器 | X / Y / Z速度RMSE (m/s) | 最终判定 |
|---|---|---|---|
| 01 / 15001 | PID | 0.042020 / 0.009880 / 0.002329 | 接受 |
| 02 / 15001 | ESTA X | 0.014489 / 0.009773 / 0.002166 | 接受，配对通过 |
| 03 / 15002 | PID | 0.043468 / 0.007829 / 0.002348 | 接受 |
| 04 / 15002 | ESTA X | 0.014795 / 0.008022 / 0.002592 | 接受，配对通过 |
| 05 / 15003 | PID | 0.044080 / 0.008101 / 0.002797 | 不接受；数值仅诊断 |
| 06 / 15003 | ESTA X | 未执行 | 首必需失败后停止 |

前两组分别满足预设XYZ速度、位置、yaw比较门槛；同种子IMU前5000行创新逐位数值差为0，不同种子不同。只对IMU播种，其他随机源未独立播种，顺序均PID先行；不是新正式论文留出集，也不能从两个开发种子推断泛化。

X误差下降伴随控制请求变化量增加：32秒窗口X加速度请求TV，PID为3.3371/3.3465，ESTA为22.4053/22.4868（m/s²）。这是逐更新请求的总变差，不是实际加速度、电机能耗或共同带宽谱；不能只报告更小误差。原验收未将TV设为拒绝门槛，本次没有临时添加或删除门槛。

5轮基础49项与核心控制检查均通过、全程无回退；最终运行器退出1。独立接触期诊断5轮均无削顶、EKF故障/切换、reference/reset变化或timing故障，ULog dropout0/无损坏。诊断脚本的`formal_accepted=false`是其固定“非验收”标签，不覆盖正式前4轮accepted。

## 拒绝原因与离线修订

第5轮37.216s有两条不同的position_setpoint_triplet：旧起飞目标valid=1/type=2，随后清空valid=0/type=5，previous/next时间及current经纬高等改变。vehicle_status同刻进入POSCTL；38.604s才发新高度交接命令，38.976s交接确认，47.056s进入观察。并非观察中目标竞争，也不是采样倒退。

Navigator的POSCTL分支将导航模式设为空并reset_triplets，reset_position_setpoint将目标置invalid/IDLE；发布时间只用hrt_absolute_time。FlightModeManager在POSCTL选手动位置任务。因此全日志存在这组消息，不足以说明后续已确认的AUTO_LOITER目标不唯一；但仅凭同刻也不能声称哪条被消费者实际取用。

protocol15把“目标使用窗口内不得有歧义”扩展为全日志任意位置不得有歧义，导致任务准备阶段正常转换被拒绝。新独立triplet16保留原triplet15/原判定：

- 全话题仍检查非空、时间类型/正值/范围、字段齐整及无倒退；不删行、不合并、不last-wins。
- 检查从handoff_ready的完整前驱同刻组开始，到hover_end边界组（含）为止；这些可能影响已确认目标的组，任意字段逐位不同均拒绝。
- 窗口前已被更晚目标替代、或结束边界后的歧义组保留并明确列为`unresolved_outside_groups`，不冒称其无歧义或已证明消费者取值。
- 原目标匹配仍为半开观察窗口；全程状态/reset/高度/故障、命令ACK、唯一发布者、三秒入口及其他话题时钟规则保持，生产控制和dt不变。

入口前驱不能仅取searchsorted最后一行；结束边界也不得拆组。12项新测试覆盖上述边界、窗口内/外歧义、previous/next字段、NaN载荷/正负零、空/错位/倒退、整数溢出及原完整链差异约束。测试退出0，完整脚本回归377项通过；此结果阶段未重跑C++，不把飞前140重复计数。

三批共10轮隔离完整链回放：series11保持3真1假（旧入口失败仍拒绝），series12的1轮和series13的5轮在候选新规则下通过。**仅用于验证工具修订；series12及series13/run05的正式失败均不改判。** 前4轮还已用原protocol15 CLI另存目录回放，均退出0。

## 证据、复现与下一步

证据：[results15](../v04/results15)。大型日志在`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/series13`；验证protocol15_precommit01/committed01，原规则回放protocol15_replay01，接触诊断protocol15_audit01，新规则回放triplet16_series11/12/13_replay01。原始日志、结果和工具输出指纹存入索引。主失败ULog80,061,033字节，SHA `94ecc612184c2677245b05b79de53b62264eddebde070a8ef3abd647b5341227`。

从仓库根设置项目Python依赖后：

```bash
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py' -v
python3 research/sta-velocity-control/scripts/replay_v04_triplet16.py \
  '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/series13' \
  --protocol-dir research/sta-velocity-control/v04/protocol15 \
  --output /tmp/v04-triplet16-replay-new
```

输出目录必须尚不存在；回放只写新目录，不执行飞行、不追认旧判定。一次只读诊断漏设外部pyulog路径退出1，补齐依赖后完成；无飞行副作用。未执行MATLAB、旧七八批全量回放或Z飞行。

EEPROM逐轮完全恢复SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无残留模拟器。累计21尝试/7接受/3组合格历史配对，但分属不同批次，不拼接宣称本次三组完成。下一步按持续授权接入新window16规则、冻结新种子及六次预算、提交/干净测试后另批验证；仍不调控制器/阈值、不push、不V05。
