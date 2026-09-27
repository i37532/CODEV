# E01-XYZ protocol01：实现与飞前冻结

2026-09-27，offline_passed / 飞行待执行，不能称三轴已验收。

起点af3edfd2bbaf3e9e6f012e77f3df92890c11615c，research/sta-velocity-control，工作区/递归子模块干净。用户明确允许插入V05→E01-XYZ→V06并持续完成普通修复/新冻结有限SITL批次，无逐次起飞授权；不改原安全/性能门槛，不push/实机/下一阶段。

完整阅读速度计划/共同规则/进度、旧共同规则、V05、Z03及Z02设计，另存三份计划快照。V05与Z03独立通过；不把分开通过称同时XYZ已通过。

## 实现与审查

新独立PositionControl::_velocityControlEstaXYZ、仅SITL AXES7准入；地面/ramp原PID、一次三轴有界原子初始化、正常空中仅ESTA、FF一次。HTE按原Z推导只补偿Z；活动速度掩码变化清状态重交接；公共映射/限幅后统一预验证再commit。旧X/XY/Z函数体保留，原位置P/PID核心、Takeoff、HTE模型、姿态/rate控制、默认值不改。详见e01_xyz/README_CN.md。

TEST4默认关闭：原sample时钟12s稳定→Z16s/XY16s/XYZ32s；新增excitation_z日志，完整消息格式1475字节（<1500）、队列8。90s观察/落地时长沿用已验收V05 protocol02完整链；新增Z输出清除/历史检查，没有重复V05的60/90秒接线遗漏。

离线审查比较原PID函数/默认值/Takeoff及2×2048步逐位参考；确认不使用Gazebo真值、不改估计器/land detector、默认PID/禁止MODE2、无并行setpoint源、正常XYZ无闲置PID/ARW。

## 实际测试与开发失败

`python3 research/sta-velocity-control/e01_xyz/protocol01/verify.py --output .../E01-XYZ/verification01`退出0：**190个不同C++，424个Python**，均从XML/实际运行输出计数，非零匹配；所有子命令退出0。包括XYZ12、XY11、真实模块27、参数保存5以及PID/核/保护/起飞/旧工具回归。SITL、测试、DONT_RUN Gazebo构建通过。

XYZ单测包括独立带滞后/交叉轴对象、正负与FF、候选/第三轴失败原子性、HTE非零倾角、XYZ约束、混合NaN、0/1/3/4/7切换/armed暂存、接触/取消/跨起飞reset及波形。对象轨迹不是Gazebo飞行或理论稳定性证明。

开发记录保留：首编译double-promotion退出2；12项新测试早期2失败（理想推力方向与真实limitTilt重构数值差、故障夹具重新解锁未清注入的无效反馈），修正映射核对及夹具后12通过。旧保护测试认为7必须拒绝，与本阶段新授权冲突，保留该失败后新增合法7/非法5断言。Python新三输出波形的二输出返回/解包、EOF逐字断言和生命周期夹具缺字段也先失败后修复；未改验收数值、未删除负例。
此前controls01退出1，controls02及verification01退出0。首编译完整原始stdout仅见任务工具输出，其后development/*.log及所有验证XML保留，不冒称每次探索都已完整外部归档。

## 首批准确预算

见e01_xyz/protocol01/execution.json。新种子22001–22003各PID→XYZ ESTA，共6次；初次种子扫描无复用，飞前重新检查。XY参数1/.2/.4/.8，Z2/1/4/6，HTE开启、共同下降.6/.55、rate0/0/DIV1/RATT0/TKO0。原启动器Iris10016/quad_w/empty_grey，仅IMU播种。
逐窗/合并64s每轴RMSE≤1.25×PID+[.02,.02,.01]，位置+ .05m、yaw+ .02rad；约束≤5%/连续≤.5s，原绝对安全/完整日志门槛保持。开发n=3不作显著性；Z/TV不要求胜出。
先提交本协议/源码，在干净提交重新构建/核验后才飞；首必需失败停批、不补飞。数据目录 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/E01-XYZ/paired01`。此报告写作时新飞行0，结果另报E01_XYZ.md。

EEPROM未变06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。未运行MATLAB/实机/V06/正式留出。最终源码完整SHA提交后写外部进度，再记录准确授权绑定并执行已获准预算。
