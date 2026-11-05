# RI01 独立数值检查结果

2026-10-24，最终证据为verification03/model_final，总退出码0；model_attempt01/02完整保留。未飞行、未登记新飞行种子、未运行MATLAB、未修改来源包。本结果不代表RI01整阶段的生产回归或SITL构建；那些由主报告另列。

## 实际执行与范围

~~~bash
python3 -B research/sta-velocity-control/regularized_ista/ri01/model/check.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI01/verification03/model_final'
~~~

最终5条子命令的完整argv、cwd、退出码和输出SHA在 [最终summary.json](results/verification03/summary.json)，全部退出0。新核用g++11.4.0严格C++14、-O2、-Wall/-Wextra/-Werror/-pedantic-errors编成共享库；Python3.10.12仅标准库。没有过滤/分片；未找到matlab可执行文件。没有运行任何PX4/Gazebo启动器。

| 检查 | 实际数量 | 结果 |
|---|---:|---|
| 来源SHA清单 | 29文件 | 原包全部匹配，exit0 |
| oracle自身单测 | 6项 | 6/6；含奇对称、三式残差、候选nu输出、一次FF、滞后精确积分、保护反例 |
| 单步float对独立double | 720组 | 最大归一化候选差1.43524e-7；三式残差1.60474e-7；预定门槛3e-6 |
| binary64参考自身残差 | 同720组 | 最大1.35466e-16；门槛2e-12 |
| 保存的MATLAB fixture | 3990行算法1 | 全部通过；算法0另外3990行不计为新核验证；不是MATLAB重跑 |
| 独立对象 | 102条，共559827有效更新 | 84条完成60s，18条按预定极小数域拒绝停止；6条不可行限幅反例保留 |

来源fixture逐项剥离FF，核对纯纠偏，再独立重建原源包的总输出限幅、外推冻结和状态限制。2464行发生保护；理想输出/应用状态分开，最大归一化raw/limited差1.09314e-6，低于3e-5；不能据此声称PX4保护已接通。详情见 [fixtures.json](results/verification03/fixtures.json)。

每次各自输入文件运行前后SHA相同，具体新内核、桥、脚本、预执行规范、来源CSV、源导出脚本与实际采样清单在 [最终inputs.json](results/verification03/inputs.json)。最终共享库SHA=157ec9c2a865387fc7b92f5f8bd7889944da62b837f7adcd5eb62069d18776ef。完整轨迹CSV留外部历史目录及verification03/model_final，仓库 [最终objects.json](results/verification03/objects.json) 保存逐条绝对路径、大小、SHA和指标；重复回归不累计独立样本数。

首次对象/fixture检查exit0后，独立代码审查发现特殊float分支边界的rho可能高于1一ulp。生产新核修为按实际求得的p形成sat/Psi，主C++单测新增该反例；本工具按完全相同规范、案例和容差重新执行attempt02。首次共享库SHA=f810b9f523f235216ccb0bf0614451a6e533e461ff685b3fbcd77779d21e8f09，首次证据在 [attempt01](results/attempt01/summary.json)，未改写。最终上述汇总数值与首次一致，不能由“原网格通过”否认该边界缺陷。

attempt02共享库SHA=5f7129d3e773554077f6ebb7a29b60ec203f79f6fedbc93ae218e8993cd97f47，保留在 [attempt02](results/attempt02/summary.json)。之后主流程又修订reset代次耗尽永久锁并作项目格式化，收尾指纹检查发现核文件不再匹配attempt02；未将旧结果冒称最终核验证。主流程重新在verification03/model_final运行完全相同脚本/桥/执行前规范，最终数值汇总一致；本文件只同步最终小证据，不修改测试输入或删除旧结果。全阶段其他验证修订见RI01主报告。

## 对象结论必须分列

102条分类：固定h理想恒扰24条、固定h层内斜坡8条、仅有限轨迹/实现一致性46条、数值域耗尽18条、不可行限幅6条。所有float与独立double对象最大速度差1.620864e-7m/s，低于2e-4；这不是102个独立统计样本，也不是飞行性能对比。

- 固定周期正/负恒扰尾均值满足2e-5m/s门槛，没有复现旧ISTA的h*d平衡。零扰长轨迹不能隐去数值域终止后宣称全60s通过。
- 固定周期斜坡存在偏差，与RI00层内推导的差均小于2e-5；不是任意扰动零误差，也不是所有误差O(h²)。XY正斜坡8ms尾均值.0002080819、理论.0002081280；Z为.00004464364、理论.00004465348m/s。
- 实测6399间隔来自RI00冻结原日志，按原顺序循环；没有把8/12ms替换成平均周期，没有新ULog或历史飞行改判。
- 测量噪声是预定正弦叠加，两级滞后为60ms/20ms精确ZOH对象；只核对列明轨迹，不能代表真实内环/电机稳定性或实际随机独立性。
- ±.05纠偏抵消不了+.15扰动，6条反例末端约6.05m/s、尾均值约5.55m/s；“检查通过”仅指正确保留不可行反例，绝不表示跟踪成功。保护输出不标记严格隐式解。

18条零扰对象在11.784–33.780s触发NumericalError（status5），当时最大绝对误差约5.151e-36m/s、nu约6.649e-35m/s²，微小增量进入float非正常数域。按照执行前规范停止且状态保持不变，没有冲零、放宽门槛、跳过坏点或凑到60s。其末尾10s是实际停止前窗口，不是计划50–60s。它们验证严格拒绝策略，不能被包装为全float域数值鲁棒性；RI02必须明确数值拒绝的保护响应，不能直接拿本结果授权飞行。

历史attempt01/02及本次最终模型工具均exit0；回归未换参数、案例或阈值。只读探索曾误查不存在的test_matlab_reference.cpp路径（exit2），随后按实际文件清单核对export_controller_reference.m；运行后源码再次修订引起的指纹检查失败及最终重新绑定如上披露。所有外部原始数据保留。
