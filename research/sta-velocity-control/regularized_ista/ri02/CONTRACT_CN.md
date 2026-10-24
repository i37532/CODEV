# RI02 执行前接口与保护约定

入口2026-10-24，HEAD `2f19cefc850ef4b77a8bcdc455aaec193f3da331`，分支research/ista-velocity-regularized。本阶段仅离线；新飞行/种子/参数调优预算0。RI00/RI01已验收；RI01随后push已核实。原R04/R05暂停。

## 保持与准入

MODE4=补偿正则化隐式速度核；识别配置不等于准入。生产PositionControl新独立私有准入false，没有参数/公共setter可打开；仅命名离线友元可测试。0/1/2/3语义和默认PID不改。新核离线仅1/3/4/7、DIV1；其余拒绝。参数复用RI00的15项但各算法独立完整配置，armed暂存取消、disarm原子生效。没有新起飞管理、上游、模型或估计器修改。

## 一次候选与保护

采用RI00 RI-1…4及RI01数值域，不改变纯核公式。每轴先求理想p/nu_candidate/a_ideal，先纠偏限幅，再原FF一次，再原倾角/总推力/Z优先/XY余量映射。按NED残差方向冻结外推nu并限状态；无约束映射差不是饱和，不使用机体mixer位或PID tracking ARW改nu。状态冻结/裁剪**不重算当前a_ideal**。全部候选和下游反馈有效才一次commitBatch，末轴错误不部分提交。

strict_axes只标记确实提交、状态未改且纠偏/下游约束均未改该轴的理想候选；未启用、priming、失败、限幅/冻结不冒称严格隐式解。真实sample重复/倒退/长停顿保持既有时间窗，重复调用不再次积分未选PID或新nu。数值域拒绝（含RI01极小数拒绝）故障锁存并拒绝发布，不悄悄冲零、保持输出冒充安全、或新增自动PID接管；disarm清状态后才恢复。

## seed / HTE

Z/XYZ保留原地面/ramp PID及单个priming PID输出。对冻结s与前一真实sample间隔h，F_h(s)=-a(s,nu=0)，seed=PID纠偏+F_h(s)；h必须在原2–40ms窗。只反解，不提交算法积分；超nu/纠偏限或映射已受限则拒绝，不裁剪成“无扰”。下一帧h/s可变化，独立测试8↔12ms，不声称精确预测下一帧。

HTE仅使用有sample/配置身份的上一实际应用纠偏/FF缓存：delta=(hover_old/hover_new−1)*(cached_correction_z+ff_z−g)。有下游约束、状态/纠偏保护、无有效缓存、未闭合事务或失效时拒绝并锁存；不以当前nu再evaluate，不重用R-STA显式反解。接受时nu与缓存一起平移并废弃旧候选，hover只在检查通过后改变；不改变PID原HTE语义。这里保证的是缓存冻结工况的映射关系，非下一帧任意目标连续性。

## 证据与回归

扩展现有selection（不新占logger槽），与status按publish_seq/sample精确关联；增加p、理想/应用nu与纠偏、发布加速度/推力、核h/seed_h、缓存sample/有效性及strict/commit/version。实际生成长度必须<1500字节，保持队列8和既有日志位；零飞行下仅声称离线生成/队列/解析验证。

新工具默认dry-run、execute硬拒绝。继承最终revision11/position11完整时钟/白名单/同刻组/reset/相对预热/增量/尾窗链；旧日志只读诊断、不改判、不作为新飞行。R-ISTA数学分析独立，不把MODE4改标3。冻结RI01参考做PID与R-STA各至少2×2048逐样本（含FF/HTE/约束/reset/重算），旧ESTA离线回归；新保护/生命周期、模块/参数/日志负例及SITL构建全部记录真实数量/退出码/失败。原始大证据外置新RI02目录。
