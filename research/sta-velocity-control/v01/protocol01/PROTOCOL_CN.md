# V01：速度选择框架与一次原 PID 起降冒烟

日期2026-09-21，起点b11068e2ddb0c6734ae566045dc096eaf7a7c834，research/sta-velocity-control。
起始工作区/递归子模块干净，已与codev远程同步；外部实时表此前“未push/领先5”是V00收尾时历史状态。
已完整读取速度计划/共同规则、实时状态、V00及恢复批次02验收；旧研究经验已在首次V00执行时读取。
本次用户仅授权V01，包括离线回归及一次PID起降冒烟；不push、不执行V02。

## 配置语义

独立参数MPC_VC_MODE、MPC_VC_AXES均为Int32，默认0。实现前全源码/msg搜索无同名项。
V01仅接受(0,0)；所有非零axes均拒绝，包括未来1/3/7。模式1/2未实现，其他模式越界。
requested保留原始有符号32位请求，不先窄化；effective只可能(0,0)。
reject为位掩码：1=模式越界，2=模式未实现，4=轴未开放，可组合。
armed期间请求与effective不同则pending=true；请求恢复(0,0)立即取消pending。
disarm后pending=false，对当前请求重新校验；非法请求继续拒绝，合法(0,0)生效。
重启从PID默认状态重新验证持久化请求；原PID仍正常运行，选择失败不重置积分。
本阶段没有可生效的其他算法，因此“disarm生效”仅验证合法PID配置，不声称测试了ESTA切换。

PositionControl::_velocityControl成为dispatcher，唯一分支调用原PID函数体；原函数体只改名称。
位置P、NaN配对、非零FF、限速/倾角/推力、垂直积分及XY ARW次序保持。
原parameters_update/set_vehicle_states/failsafe函数文本逐字节核验未变；原PID增益和HTE更新独立于pending。
Run在原control_mode更新后读取选择参数；选择状态按原local_position回调处理，未改时间源或滤波。

## 最小日志

新增velocity_ctrl_selection，每个消费的local_position样本发布一次：timestamp/sample/input_timestamp、
publish_seq、requested/effective mode/axes、pending/reject、armed/enabled和pid_calls。
pid_calls为本回调实际PositionControl.update调用数（含失败后第二次调用），不是成功更新数。
此消息仅用于V01选择验收；V03所需完整速度内核/保护诊断尚未实现。
生成格式字符串长度远小于1500字节，非padding载荷49字节；实际ULog解码仍为必需验收。
默认profile请求100ms，HIGH_RATE请求全发布率；保留原profile位。实际订阅/记录覆盖以日志为准。

## 离线测试与参考来源

test/v00中的PositionControl、ControlMath和Takeoff六份源文件取自V00当前基线b11068e2dd，
同时核对V00 verification04外部原始参考；仅重命名标识符/头文件并添加friend用于观察积分。
verify_v01.py检查每个转换后的完整文件及源/参考SHA；参考只用于BUILD_TESTING，不链接SITL。
两组各2048步：10ms固定步长；8/12ms交替并叠加拒绝请求。逐样本比较成功标志、
状态/积分/增益/限制、最终速度/加速度/推力、姿态四元数/角度；有限浮点逐位相同，NaN按未启用语义比较。
序列覆盖非零速度/加速度FF、XYZ、成对/半组NaN、纯加速度、ARW/推力饱和、HTE、
原Takeoff与独立冻结Takeoff斜坡/状态、显式reset、EKF目标/测量平移、Z预混合状态、
无效输入后同一dt的failsafe式二次update。逐样本检查第二次积分保持原语义。
参数联动/HTE及模块完整函数未变的静态验证，与回归中实际增益/限值变化分开记录；
序列是核心+Takeoff测试驱动，不冒称完整运行了所有Module Run分支。

额外用例：有符号极值/越界/未实现模式、所有非零轴掩码、armed暂存/取消/disarm拒绝、
重启请求重新校验；功能测试通过真实param_export/import验证BSON保存/重载，再由新selector校验。
verification01测试链接失败：新功能测试未提前链接parameters，静态库顺序导致daemon stub未解析。
按现有ParameterTest的依赖补齐后，verification02构建和44项C++、37项Python全部退出0；旧失败保留。
44=原Position15+ControlMath9+Takeoff8+Rate1+Dispatcher4+VelocityControl6+参数功能测试1。
37项Python包括6项选择日志拒绝测试；不将构建或重复执行算作更多不同用例。

## 唯一一次飞行

先提交本协议/源码并确认干净，再DONT_RUN重建固件和Gazebo；实际SHA通过--source-head传入，
固件启动前后必须同指纹。准确清单只有run01，最大尝试1、seed=null、原默认随机引擎、1倍lockstep。
沿用sitl/run.sh --headless --backend gazebo --model iris；empty_grey.world、Iris10016/quad_w。
不使用DP1000实机。飞行源是原flight_mode_manager；运行器仅commander命令、中性RC及心跳。

继承V00恢复批次02的任务及全部安全/日志阈值：预热≥30s、MIS_TAKEOFF_ALT=2.5、
CODEV起飞完成转POSCTL后请求Hold、稳定3s、悬停60s、auto:land直到上锁。
V00实际Hold高度约1.92–1.95m，本任务沿用相同流程和±1m悬停包络；不承诺精确2.5m。
原位置P/XYZ速度PID/姿态/rate PID；速度MODE/AXES=0，rate MODE/AXES=0、DIV=1、RATT_TEST/TKO_MGT=0。
所有原MC_/MPC_/SYS_VEHICLE_RESP值继承V00冻结参数；不调参。
EEPROM完整原字节备份、停机后精确恢复；SDLOG_PROFILE保留并OR16、DIRS_MAX1000保护旧日志。

机器清单protocol.json列出完整阈值。新增selector必需门槛：全飞行请求和生效均PID、pending/reject为0；
publish_seq不缺号，sample/input时间严格递增，至少600条、最大间隔≤250ms；
enabled时pid_calls=1，disabled时=0，必须有armed+enabled样本。原49项V00门槛全部保留。
饱和和perf统计采用已披露勘误另存，原V00指标副本仍保留；不据描述统计调整门槛。
任何必需检查失败即停止，保留失败，不补飞、不加次数、不改门槛。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
DONT_RUN=1 make px4_sitl_default gazebo_iris -j4
python3 research/sta-velocity-control/scripts/run_v01.py --execute \
  --source-head '<本协议实际完整SHA>' \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260921/V01/series01'
```

不带--execute只打印协议；输出目录已存在则拒绝覆盖。一次完成或失败后单独提交结果报告，
更新外部进度表完整SHA并停止。本文件不预填尚未进行的飞行成功结果。
