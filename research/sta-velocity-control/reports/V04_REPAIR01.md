# V04 REPAIR01 — 起飞目标缓存、同帧重算与诊断修复

日期：2026-09-23。状态：**本次修复离线验证通过；V04飞行验收仍failed / needs_revision。**

用户在离线诊断后回复“允许”，授权先修复并做离线回归，暂不飞行。本次不修改高度门槛/飞行协议，不使用剩余5次预算，不进入V05，不push或实机部署。旧失败不改判，ESTA实际飞行仍0次。

## 1. 版本与证据范围

- 起点：`research/sta-velocity-control`，HEAD `640a5857a28b8045ea91690a33748446ba4ce275`；主仓库/递归子模块干净。完整读取速度计划/共同规则、进度、V04前置及离线诊断，未回退/清理原改动。
- 旧飞行源码`67b07d75a98bc3ddf502a779e6cf80f068a1e0e6`及protocol01、results01保持不变。新修复提交完整SHA写外部实时进度表，不在本报告自引用。
- 新证据根目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260923/V04`；离线诊断为offline_rootcause01，修复验证为repair_verification01/02/03。小型证据位于[v04/repair01](../v04/repair01/evidence.json)。
- Gazebo子模块仍`822050a7ab6fd87972e59f16312f451bce217a56`，模型/world/插件不改；只编译Iris Gazebo SITL，未启动仿真/实机。无MATLAB/Octave执行。

## 2. 已定位的根因

旧失败日志31.980s地面抑制把持久_setpoint改成位置/速度NaN、加速度(0,0,100)。31.988s无新trajectory，起飞状态进入ramp，程序又清除Z加速度；导致Z位置/速度/加速度目标全NaN，第一次控制update失败。状态有效标志和速度/导数均正常，并非ESTA增益问题。

原failsafe的200ms迟滞尚未触发，零初始化的重算目标没有被填充，形成位置(0,0,0)、yaw=0的意外请求；重算最终valid并不证明没有瞬态。同时实验激励器在同sample再次update，被误归为时钟异常，锁止至disarm。

前置offline_rootcause01用实际内核和V00冻结参考完成7项诊断复现，推力/加速度与原日志通过EXPECT_FLOAT_EQ对照；这些7项属于前一轮诊断，不累计到本次104个修复回归。初始失败输入由缓存时间和源码重建，不冒称旧ULog直接记录了首次输入。

## 3. 实际改动与行为边界

### 3.1 缓存与本帧目标分离

MulticopterPositionControl::Run保留原消息接收及EKF delta对缓存的调整，再复制frame_setpoint。地面/接触抑制、ramp的Z加速度FF禁用及本帧Z速度混合只处理副本。无新trajectory时不再继承被地面抑制破坏的目标。

原Takeoff状态机、ramp数值、位置P、PID/ESTA控制公式、HTE更新函数、滤波和参数更新函数不变。**这不表示模块行为与旧版处处相同**：地面到ramp无新目标的病态帧就是本次有意修正的差异；未来两算法均须在相同修复源码上建立新批次对照。

### 3.2 第一次失败即生成明确fallback目标

原200ms迟滞保留用于_in_failsafe及警告时序；目标生成不再等待迟滞。先全部置NaN，再沿既有策略：有效XY速度及导数时给XY零速度；否则给XY零加速度并请求下降；有效Z速度及导数时停速或保留下降速度，否则沿用Z加速度0.3m/s²分支。yaw保持NaN，由原控制器使用当前航向，不请求零航向或世界原点。

这里的零速度是明确的停速目标，**不是位置保持保证**；盲降分支也不是新验证的实机安全方案。新增导数有效性检查，因为原速度PID也依赖v_dot。若最终重算仍无效，PID和ESTA均禁止发布该无效最终输出；停止发布后旧指令可能暂留，不能称安全悬停。实验必须停止。

不切换到另一算法；ESTA真实失败继续锁存直到disarm，同一sample不重复提交nu。原PID正常数学/积分次序不变；异常路径不再声称与旧模块完全等价。

### 3.3 激励时钟与失败通知分离

每个Run的传感器sample只调用一次激励update；失败通过abort通知，不再用同sample第二次update表示失败。abort仍锁止实验，不能通过修复假时钟故障而吞掉真实控制失败。实际重复/倒退sample、超过40ms间隔、开始后门禁退出仍锁止，disarm清除。

### 3.4 首次失败日志

sta_velocity_ctrl_status新增下表字段。原向量仍表示最终调用；first_*明确保留第一次调用信息，不能用最终成功掩盖前一次失败。

| 字段 | 解释 |
|---|---|
| first_fail | 位1 XY输入配对错误；2受控位置测量无效；4受控速度/导数无效；8加速度输出无效；16推力输出无效；32 ESTA故障锁存 |
| first_input | bits0–2原位置目标、3–5原速度FF、6–8原加速度FF、9–11消费速度、12–14消费导数是否有限 |
| retry_result | 0未重算、1重算有效、2重算仍无效 |
| excitation_fault | 锁存位1传感器时钟异常、2开始后门禁退出、4真实控制失败；不是当前是否有非零激励 |

生成格式由1316变为**1403字节**，低于1500，队列仍8。新增合成ULog的pyulog编解码测试通过；真实uORB模块测试读取了新字段。**未取得新版本的飞行ULog或实际logger运行证据**，不能把合成ULog说成真实飞行日志。

## 4. 验证方法及实际数量

最终repair_verification03：**104个不同C++、58个Python**，所有归档命令退出0，无disabled；重复执行不累计样本。详细命令/退出码见[evidence.json](../v04/repair01/evidence.json)，模块输出见[VelocityModule.log](../v04/repair01/VelocityModule.log)，Python见[python_tools.log](../v04/repair01/python_tools.log)。

- 原92个C++：PositionControl15、ControlMath9、Takeoff8、RateControl1、Dispatcher4、VelocityControl6、参数2、速度核9、公共保护12、角速度STA核11、诊断输入3、VelocityEsta9、历史候选探针3。
- 新增12个：10个真实模块Run/uORB用例，2个激励原因/时钟用例。
- 两组各2048步原PID与V00冻结参考逐样本位级相同；正常PID数学、原加速度映射和ESTA X公式的函数文本亦核对不变；Takeoff及参数源文件逐字节不变。
- 新模块测试覆盖50Hz目标/8–12ms回调、无新目标帧进入ramp、旧/新目标与EKF reset、地面接触/退出重入、真实无效目标、缺测恢复、迟滞边界、无效导数/速度降级、PID无效重算不发布、ESTA失败不二次提交/不接管及disarm reset。
- 模块测试同步调用真实Run并通过真实uORB发读消息；**仅在测试链接时替换备用定时器调度/取消**，防止异步回调抢跑。模块、控制器、Takeoff、滤波、迟滞及uORB不替换。工作队列管理器在测试进程内启动/退出，没有PX4飞行进程或Gazebo，也不声称验证了实机调度时序。
- Python原57项继续通过，新增1项根据实际生成格式构造合成ULog，核对first_fail/first_input/retry_result/excitation_fault等真实解析结果。

复现（每次使用不存在的新输出目录）：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/scripts/verify_v04_repair.py --output '/绝对路径/新的离线验证目录'
```

该入口执行SITL构建、真实非零测试和`DONT_RUN=1 make px4_sitl_default gazebo_iris -j4`，不飞行。旧verify_v01/verify_v04仍保留“failsafe必须原样”的历史断言，不能拿它们原地验收这次获准的上游修复；新入口明确记录failsafe语义有意改变，同时保留原数学/参考/参数审计，不静默放松旧协议。

最终构建固件SHA-256：`1faf92cf4607af9f35570d759e1177ada92ad949257778e2a4f539d3639802b1`。这是提交前构建，来源为本次diff及归档文件指纹，不冒称在最终提交SHA上飞过。

## 5. 开发失败及保留范围

早期探索包括：新模块测试缺MODULE_NAME导致make退出2；未初始化HRT的同步夹具阻塞，确认自有测试进程后SIGTERM终止；gdb附加被系统限制，未绕过；诊断订阅队列读到上一帧导致3个夹具断言失败；用四元数单分量代替yaw及无效注入被setter约束导致2项断言失败；工作队列异步关闭检查失败。已改为测试专用定时器替换、同步队列生命周期、读取最新诊断、比较实际yaw和显式非法增益注入，不修改飞行门槛。

合成ULog初次多写了末尾padding，pyulog拒收；按logger的o_size_no_padding构造后通过。早期输出仅部分保存在本次工具记录，不声称每次探索都有完整外部原始日志；repair_verification01/02/03的完整命令、构建/测试/XML输出均保存。01为102C++/57Python，02为104/57，03为104/58，以03为最终数量。

## 6. 指纹、提交与停止

新130份外部诊断/验证文件按[artifacts.sha256](../v04/repair01/artifacts.sha256)全量核验退出0；索引SHA-256 `ff79b1dac7e94be24e6679eb960574484a5e36b1ae21050a696d26d6c4c8ee24`。旧V04全部243份指纹另行核验仍一致。

EEPROM仍1129字节，SHA-256 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，与原备份相同。没有更改持久化模式/默认参数，未产生新运行参数证据；最近真实rate PID验证仍为旧V04日志，不能声称本次无飞行却重新核验了飞行模式。

diff已按生产修复/消息/测试/新离线入口/报告与小证据分组审查；明确路径提交后在外部进度表写完整SHA。本次修复仅离线通过，不能据此宣称ESTA飞行通过或实机安全。

**下一步**仍需单独修订并冻结高度任务：区分导航起飞完成与到达实验2.5m；保持唯一目标源、明确入口/稳定窗口/超时和新批次预算。原protocol01及失败结论保留，不直接续跑剩余5轮，不放宽高度门槛，不自动开始新飞行或V05。
