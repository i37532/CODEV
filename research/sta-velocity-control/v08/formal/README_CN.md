# V08冻结的下一阶段正式实验包

本目录只冻结，不代表正式试验已经运行。200项outcomes初值全部unattempted，没有虚构误差或成功率。
实际执行属于V09，需要在该阶段复核源码/固件/模型/插件/分析器与独立输出目录，不能运行训练或先导入口冒充正式试验。

## 准确预算

五场景顺序：hover、固定yaw figure8、figure8+平滑heading、figure8+水平外力、figure8+质量增加10%（惯量Q6(1.10 I)）。
每场景PID/XY ESTA×41001–41020，合计200。每对种子内算法次序交替；不是100个独立随机种子，而是跨场景复用20个种子块。
不纳入DIV2/4、XYZ ESTA、ISTA或因素全组合。原位置P、Z速度PID、姿态/rate PID、HTE、传感器和滤波固定。

参数锁定于完整training02选出的pid2/esta0；validation与pilot不能重选。旧M10、速度研究及本阶段所有失败都是已见开发资料，不能称未见留出。
新24训练均等；旧中止批次和后续系统/分析修订产生的额外开发次数另列，不把历史成本包装成完全相同。

## 预定判据

主窗64s：实际消费s=v−v_sp，按sample间隔先算每轴RMSE，再平均XY，单位m/s。
位置P仍运行，不要求PID/ESTA最终v_sp逐样本相同；反馈误差不等于真值误差。
每轴、Z/yaw、位置、约束、TV/频谱和成本另列。TV按真实更新，原生频谱与抗混叠共同0–7Hz分开；TV不是能耗，宿主耗时不是板级CPU/WCET。
所有原数值安全与开发门槛、完整主诊断、消费目标、限定下游部分覆盖和时钟规则保持；缺失姿态输出明确未证实，不插值补造。

首次必需失败停止整批，原失败和余下unattempted保留；不能自动补飞、增加种子、换参数或挑时间窗。
分列飞行失败、数据无效与未执行；“接受率”分母为实际尝试，不把未尝试当事故。
日志无效不自动等同飞行失稳，但不得进入完整配对主指标。完整200清单不可删行，缺失不填0。

主比较按同scene/seed完整接受对，差值=ESTA−PID；五场景共享同一20种子块重采样。
固定20000bootstrap/分析种子48001，报告95%及五比较校正的99%区间、配对n/缺失、空重采样次数。
Wilson95%仅描述实际尝试接受率；噪声源/主机调度并非完全IID。接受条件化偏差和小样本限制必须披露。
至少3/5场景满足均值相对改善≥10%、绝对≥.001m/s、99%差值上界<0，且接受率/非命令轴/安全均不退化，才符合预定“大部分改善”；数据不支持就如实报告。
实现保守地另要求200项全接受才输出majority_condition_met=true；有任何缺失仍提供可用配对描述/区间，但不得自动给“大部分改善”验收标签。
这是正式数据前固定的更保守结论门禁，不是飞行数值门槛调整。percentile bootstrap区间的覆盖只是近似，Bonferroni不能修复小样本/条件化选择偏差。

20种子是本协议固定预算。precision_and_development.json用各3个开发配对预测2.093×sd/√20半宽，估计很不稳定，不是充分功效证明，不能据正式结果调样本量。

## 冻结证据

manifest记录逐轮场景/种子/顺序/参数/外力相位/质量比例；execution和scenario.py明确惯量Q6规则，约1.332ppm的量化偏离，不称严格全惯量同倍率。
名义/外力先导来自protocol04，修订质量门来自protocol05，原失败保留，不合称一个同源码18轮批次。qualification.json明确各门来源。
qualified参数与代码、33子模块、原Iris/world、seeded IMU、独立外力插件及其依赖均有SHA。
运行前按固定manifest创建新目录，不覆盖V08原始数据；每轮重启、检查rate实际PID、备份/恢复完整EEPROM，沿用项目Iris启动器。
保存原始ULog/目标/参数/force.csv/loaded_model.csv、实际命令及退出码；分析必须验证同一任务sample时钟与模式/参数，不仅解析出曲线。

## 入口（本阶段仅离线）

仓库根执行前沿用项目Python环境：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/v08/formal/run.py --source-head "$(git rev-parse HEAD)" --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-V09-FORMAL01'
```

默认只打印200项清单，不创建仿真实例/运行目录。V08任何authorization均被拒绝；只有用户另行启动V09、核实干净HEAD与构建/资产/种子并提供新的绑定授权才可用--execute。不要自行复制V08记录改字。
逐轮实际目录由ledger给出（run01…run200），逻辑ID为manifest的run001…run200，不用字符串拼接猜日志位置。
每轮独立解码入口：formal/analyze.py 原运行目录 --output 新回放目录；完整回放后，用formal_package.py collect --manifest manifest.json --batch 正式批次目录 --output 新outcomes.json。
再运行formal_package.py analyze --manifest manifest.json --outcomes 新outcomes.json --output 新summary.json。输出路径必须不存在。
collect保留全部200行，首失败后未运行均unattempted；失败默认保持failed，不凭猜测改成数据无效；任何人工分类需要独立原因/原证据。
formal_package聚合不代替ULog全链校验。zero_holdout_statistics_reference.json只是全未执行的离线测试，0接受且无结论。
种子审计只豁免明确哈希登记的计划，及文件名zero_holdout_statistics.json且内容逐字等于此全未执行参考的离线验证副本；没有整目录豁免。
