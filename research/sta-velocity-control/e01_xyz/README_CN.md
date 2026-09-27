# E01-XYZ：三轴集成与验收

2026-09-27，用户授权插入V05与V06之间。当前是开发/飞前协议，尚不能称三轴验收通过。

## 范围与前置

起点af3edfd2bbaf3e9e6f012e77f3df92890c11615c，research/sta-velocity-control，进入时工作区/递归子模块干净；Gazebo822050a7ab6fd87972e59f16312f451bce217a56。
V05完成XY ESTA+Z PID，Z03单独完成Z ESTA+XY PID。这里才集成同时XYZ速度ESTA，不是三轴角速度。
用户授权普通相关修复、新冻结有限批次持续推进，不逐次请求飞行；失败停批、保留记录，不补飞/放宽门槛、不实机、不push、不V06。plan/保存新快照，旧v1不覆盖。

## 接线设计

- 仅SITL MODE1/AXES7；默认MODE0/AXES0，MODE2及掩码2/5/6拒绝。位置P、姿态、rate0/0/DIV1不改。
- 地面/ramp原PID；首个有效空中样本计算一次PID，分别令 `nu_i=(a_pid_i-a_ff_i)+lambda1_i*sqrt(abs(s_i))*sign(s_i)`。限值内、三轴映射无削顶才原子写入；该帧不积分ESTA。正常空中不计算速度PID，FF一次。
- 三轴状态独立；任何候选、反馈或第三轴失败都不能部分提交。倾角/总推力及Z优先XY余量保持原映射；只冻结加深实际约束的ν增量，不套用PID tracking ARW。
- 全XYZ配置出现速度/加速度混合目标时，活动掩码变化先清状态、显式重新交接；无速度轴使用自己的加速度FF。此类转换仅离线回归，正式低幅任务要求完整XYZ活动、一次交接。
- HTE仅Z补偿：固定之前消费的误差、FF及XY需求，`delta_nu_Z=(H_old/H_new-1)*(a_current_Z-g)`；a_current用已提交ν重算。其他轴状态不动。超出状态/纠偏域、无效HTE或饱和不宣称连续。
- 同一sample重算不二次提交；故障锁止直到disarm，无隐式PID回退。恢复后重新交接，无输出不是安全悬停。
- 发布/采样双时间与旧PID dt保持；ESTA用真实sample差2–40ms。推力映射代理不是实测加速度。

## 冻结低幅任务

沿用项目Iris启动器、quad_w、empty_grey、唯一Navigator→FlightTask目标、2.5m和固定yaw。90s观察及原落地链不改时长。
默认关闭TEST4，稳定12s后：Z16s→XY16s→XYZ32s；每窗光滑零面积正弦，周期8s，水平范数≤.2m/s、Z≤.1m/s。没有新增外部setpoint发布者。
XY沿用1/.2/.4/.8，Z沿用2/1/4/6。新22001–22003各PID后ESTA，共6次，首必需失败停。种子是否全新由飞前扫描决定，不能以编号猜测。
逐窗及合并64s逐轴RMSE门槛1.25×PID+[.02,.02,.01]；位置+ .05m、yaw+ .02rad，其他原安全/日志/约束门槛不变。仅IMU播种、固定顺序、n=3开发，不能作正式显著性结论。Z03误差/TV未优于PID，本次不保证改善。

## 入口

仓库根目录配置`.px4-python`及旧M00 pymavlink依赖后：

```bash
python3 research/sta-velocity-control/e01_xyz/protocol01/capture.py
python3 research/sta-velocity-control/e01_xyz/protocol01/verify.py --output <新的外部验证目录>
python3 research/sta-velocity-control/e01_xyz/protocol01/run.py --source-head <冻结完整SHA> --output <冻结目录>
```

最后一条默认dry-run；实际执行必须`--execute --authorization <与源码/协议/预算绑定的授权JSON>`。不应手动绕过清单/指纹/种子守卫，也不重复运行已消耗目录。
最终报告与合格配置在真实六轮/三对和独立回放全部通过后生成。
