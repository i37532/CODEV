# V06-SL：SITL 软着陆专项结果

2026-09-28，**passed（限定 Iris 弹性接触模型的开发起降验收）**。不代表实机起落架验证，不代表PID/ESTA全面性能优劣，V06三任务18轮仍待另批验证。

## 做了什么

保留原速度/位置/姿态/rate控制律、HTE、滤波、估计器与land detector、全部原数值安全/性能门槛。仅在研究运行器生成独立Iris派生模型：base collision kp2500 N/m、kd50 N·s/m、max_vel.2m/s、max_contacts4；质量/惯量/几何/摩擦不变。原模型/world、生产src/sitl/Tools默认文件零修改。原.6/.55m/s下降参数不变，两算法共用同一新接触条件。

原硬接触会将下降速度在很短时间内停止，发生超过16g的IMU截幅；本专项增加有界接触柔度/阻尼，降低峰值，不屏蔽传感器或EKF故障。新条件不能与旧硬接触数据混为同组，也不能当作已标定的真实起落架。

另补上锁后只读日志尾段收集，等待所有健康话题真实结束边界，保留原landing_health严格检查；15秒墙钟超时拒绝。未延长空中任务，未改控制器dt、发布频率或日志时间戳。

## 版本与真实数量

| 内容 | 记录 |
|---|---|
| 原研究起点 | 9178972fd6f6e0cda87b24ed34374c71f8a7190b |
| 初始专项协议/源码 | 5bee3023d0dab41489ec896b6307688e954c062c |
| 首批失败结果 | 52276854f49ec90fb65832290330d716edd16221 |
| 最终协议/实际飞行源码 | 94da9279307147154c1bc89de161f3b46b1c6ac9 |
| 最终固件SHA-256 | 4344902ecbe0d2e0de912b3e8ab4651fb9418ecd73181d7b6060e992d1ef6055 |
| Gazebo / 原模型子模块 | 11.10.2 / 822050a7ab6fd87972e59f16312f451bce217a56 |
| 分支 | research/sta-velocity-control |

- 被动Gazebo：20个场景（原/候选×.55/.7×roll0/±5/±10°），每个2秒/500步；最终ODE固定种子26928重跑20次，CSV与前次逐组一致。10候选均过；原10组是诊断对照，不要求满足候选门槛。不是无人机控制飞行。独立一维对象18组合通过。
- 最终干净源码 **196个不同C++、461个Python** 实际通过，SITL/Gazebo构建和664资产检查退出0；不重复累计历史数量。7项尾段测试覆盖真实缺口、超时/故障/重新解锁/缺起点等负例。
- 专项首批：25001首轮PID接受；第二轮XYZ ESTA完整起降但selector缺结束边界拒绝；实际2/6，1接受/1失败/4取消、0对。
- 专项最终批：26001–26003，每种子PID后XYZ ESTA，实际 **6/6接受、3/3配对通过**，无本批失败/补飞/调参。专项合计8尝试、7接受、1数据验收失败，不能把两个批次拼接成最终重复组。
- 6轮独立完整回放退出0、metrics逐字一致。首批也独立回放：PID退出0；数据失败退出1且原metrics一致，整体回放校验退出0。没有追认历史失败。

## 最终六轮

每轮原项目启动器、重启预热、2.5m目标交接、固定yaw悬停90–92s、降落上锁。实际MODE0/AXES0与MODE1/AXES7，全部rate PID、DIV1、旧实验关闭；原PID/XYZ候选不调参。

| 轮次 | 算法 | IMU种子 | 记录的加速度各轴绝对峰值最大值(m/s²) | 结论 |
|---|---|---:|---:|---|
| 1 | PID | 26001 | 56.20 | 接受 |
| 2 | XYZ ESTA | 26001 | 53.39 | 接受 |
| 3 | PID | 26002 | 51.14 | 接受 |
| 4 | XYZ ESTA | 26002 | 50.97 | 接受 |
| 5 | PID | 26003 | 66.01 | 接受 |
| 6 | XYZ ESTA | 26003 | 55.64 | 接受 |

每轮三IMU无clipping、六EKF无fault、主实例保持0，原reset/参考/时间/模式/输出检查通过，12份ULog无记录dropout/损坏。尾段采集实际遇到pending并等到后继selector记录才通过，未外推缺失段。

接触候选在被动测试的峰值61.21–97.81m/s²，原接触157.13–234.78m/s²；这只是同一被动夹具对照。正式飞行峰值不可直接拿不同旧种子飞行计算严格配对改善率。

本批64秒悬停速度RMSE均值(m/s)：PID `[.008744,.009071,.002951]`，XYZ ESTA `[.014480,.017147,.009788]`。ESTA三轴误差仍较大，但在原加性开发门槛内。加速度请求TV分别 `[5.838,5.901,7.602]` 与 `[47.051,51.185,270.292]`，不是能耗；不把软接触通过写成算法胜出。样本仅3对、IMU播种，其他随机源/宿主时序未独立控制，不作论文显著性结论。

## 复现与证据

完整协议：v06/sl_protocol02；[合格接触配置](../v06/soft_landing/qualified_contact.json)绑定控制源码、固件、模型派生器、原始日志与6轮指标SHA。大日志仅外部：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06/soft_landing`。passive01/02/03、两批series、verification、replay及全部失败保留。仓库results02保存316份原始工件指纹和小摘要；独立回放/验证证据另列。

实际执行（预算已耗尽，不重复飞）：
```bash
python3 research/sta-velocity-control/v06/sl_protocol02/verify.py --output <新目录>
python3 research/sta-velocity-control/v06/sl_protocol02/run.py --execute --source-head 94da9279307147154c1bc89de161f3b46b1c6ac9 --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06/soft_landing/series02' --authorization '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06/soft_landing/authorization02.json'
python3 research/sta-velocity-control/v06/soft_landing/replay.py --protocol sl_protocol02 --batch <series02> --output <新回放目录>
```
需项目`.px4-python`及原M00依赖PYTHONPATH，具体命令/退出码在evidence。所有运行前后完整EEPROM恢复 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无残留仿真。

开发期依赖导入、未启动物理线程、测试单复数计数、mock路径失败已在飞前报告披露；不是零失败开发。未执行MATLAB、实机、ISTA、V07或push。结果明确范围提交，SHA由外部进度记录；下一步另冻新18轮三任务，不沿用旧批余量、不混入专项6轮。
