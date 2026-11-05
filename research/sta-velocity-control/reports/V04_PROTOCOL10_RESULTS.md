# V04 protocol10 / series09：首轮降落期 EKF 切换，按协议停止

2026-09-26。**V04仍 failed / needs_revision。计划最多6次，实际1次PID尝试、0接受、ESTA0、配对0；剩余5次停止，没有补飞。九批累计9次尝试、0接受，历史结果不改判。**

## 1. 授权、源码与真实验证

用户“是”确认上一轮申请：先冻结和验证干净源码，再以9901–9903各PID→ESTA X最多6次执行。协议/源码提交：`d7090c4bc17eae80b88181c8e32dd0ac59d1b868`。干净主仓库/递归子模块通过核对；没有改控制律、控制器dt、参数候选或数值安全/性能阈值。新运行器/完整分析器接通已离线验证的landing10，原flight11仍禁用。

execution SHA：`ca1c30db058dcc346130fa5062f6397591967b95df812ba5839e356900f28986`。
实际新提交构建固件 SHA：`29f0c6121f7d82b30693ce14bead61c15257c0fde5581521dbb22f72d4bc96ca`。
授权回执、现场参数、295项资产、6项插件依赖、工具版本与递归子模块见[证据目录](../v04/results10/preflight.json)。只限Iris10016 / quad_w / empty_grey.world，1倍速项目Gazebo启动器；不是DP1000实机。

外部数据根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04`。

| 实际命令/证据 | 结果 |
|---|---|
| `verify_v04_protocol10.py --output .../protocol10_committed01` | 退出0；SITL/测试及DONT_RUN Gazebo构建成功，无额外飞行 |
| 控制/转换链回归 | 109+11=120个不同C++通过；相同11项sanitizer复跑不重复计数；2048帧旧合法转换等价、旧缺陷负对照预期退出1 |
| 干净提交Python回归 | 347项，25.383s，退出0；新增13项接线/授权/预算/完整分析正负例 |
| 旧日志回放 | 八批旧job仍拒绝、284份原输入不变，不改判 |
| `run_v04_protocol10.py --execute --source-head d7090c4bc17eae80b88181c8e32dd0ac59d1b868 --output .../series09 --authorization .../protocol10_authorization01.json` | 退出1，首轮失败即停止 |
| `audit_v04_protocol10_result.py .../series09/run01 --output .../protocol10_audit02` | 16项只读证据核对符合实际，退出0；不是新增飞行或控制单测，不等于飞行通过 |
| `analyze_v04_protocol10.py .../series09/run01 --output .../protocol10_reanalysis01` | 退出1，accepted=false，缺少landed_disarmed；未伪造结束事件 |
| 结果阶段全部Python再回归 | 347项，26.919s，退出0，不与前次相加 |

未执行MATLAB/Octave、ESTA飞行、额外冒烟、调参、V05或实机。不push。

## 2. 首轮实际发生了什么

种子9901，原速度PID MODE/AXES=0/0；真实日志rate MODE/AXES/DIV=0/0/1且inner_valid=1。持久参数及运行前检查RATT_TEST=0、TKO_MGT=0，日志profile147保留原位。不是ESTA不稳定的证据。

| 事件 | 仿真时间 |
|---|---:|
| 起飞命令事件 | 30.964s |
| 显式高度目标/交接完成 | 39.684 / 40.004s |
| 观察窗口 | 48.676–108.796s，共60.120s |
| 发送降落前读到的时间下界 | 108.944s |
| 原始DO_SET_MODE降落命令 | 108.948s |
| 原始AUTO_LAND状态 | 108.952s |
| 最后通过的降落监视证据 | 113.376s |
| selector切换 | 113.444s：0→1；113.448s：1→3；113.460s：3→0 |
| 宿主最后样本/检出reset | 113.624s |

修复后的监视器实际处理19次降落轮询，已记录原始命令与AUTO_LAND/诊断匹配，不再把旧CLI Hold与新Gate混判。最后通过时累计443条预期Gate记录，限定该前缀的独立原始回放也通过；不能把此部分通过说成整轮降落通过。

随后发生真实reset：113.448s，xy计数2→4、z 0→2、vxy 2→4、vz 1→3、heading 3→5；113.456s再次增加。ref_timestamp未变，但ref_alt短时从488.4864807到488.4265442m再返回。原始完整航向检查亦拒绝 `Coordinate/reset changed: ref_alt`，因此不是仅CLI打印表示误差。

113.448s同一诊断中，timestamp_sample=113.440s、raw_dt≈−0.004s、timing=2、excitation_fault=3。保留该采样时间倒退，没有clamp或删除。first_fail/retry_result/fault/sta_fault/failsafe旗标为0，**不能据此宣称没有异常**；timing和激励保护已提供独立异常证据。最终landing组件因timing拒绝符合保护规则。

原始selector另有两条不同实例记录同为113.448s；当前非姿态严格发布时间规则仍拒绝。未给selector新增白名单或去重。旧data访问器会先检查整个话题时间，因此对完整文件请求“截至hover_end”的航向回放也会被后续selector同刻记录拒绝；本报告不将其改成悬停整链通过，也不据此改写冻结分析器。

最后原始状态仍AUTO_LAND/armed，landed=0、ground_contact=0；没有落地上锁事件。关闭自有仿真不等于成功着陆。失败错误为 `CLI reference representation changed: xy_reset_counter`。

## 3. 指标与结论边界

诊断话题单独回放的32秒激励窗口有3200样本；X/Y/Z速度RMSE约 **0.042777 / 0.009522 / 0.002549m/s**，约束占比0。观察诊断6012条、约100.003Hz，最大间隔12ms，内环年龄0–4ms。仅作为未接受运行的描述，不是通过验收的PID基线，更没有ESTA对比结论。

两个ULog均无报告dropout/损坏。仍不满足完整任务、reset和时间门槛；“无dropout”不能抹掉真实倒退/同刻消息。

| 原始ULog | 字节 | SHA-256 |
|---|---:|---|
| 07_40_28.ulg | 163556 | 5c9a44d3da6f4517e2c53fce67bd7561d2a1584f4b812884101825a63798abbd |
| 07_40_29.ulg | 35391199 | 96db142fdfc5449c74ab0c86e46cae39d380caee51df31690280207b285a3403 |

[94项外部工件索引](../v04/results10/artifacts.sha256)包含日志、结果、失败诊断、授权、验证索引；两份完整验证索引继续指向其所有子工件。参数完整恢复SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无残留模拟器。

诊断开发失败也保留：audit01退出1，14项中3个预设正向断言不成立（未裁剪完整话题影响早期窗口、最终timing异常、故障旗标与timing混称）。audit02仅修改**新只读诊断的预期/说明**以记录真实拒绝，并增加前缀证据和负dt检查；没有修改飞行检查器、门槛或原判定。第一次大型结果汇总超出工具输出长度，JSON解析失败，未改文件；改为94项直接索引加两份传递索引，数据未丢弃。此前首次13项接线测试因缺冻结文件失败已在实施报告记录。

## 4. 停止与建议

当前真正阻塞是：**降落期多次EKF切换/reset及样本时间倒退**，而非已修复的旧CLI/Gate匹配。现有数据证明事件存在，但还不能确定切换触发原因或责任层；IMU0转换修复并不保证估计器永不切换。不能靠再换种子重飞或放宽reset条件绕过。

建议下一步另行授权**只离线审计selector切换条件、各实例IMU/创新/时间序列和本地位置发布到速度控制的时间交接**，先确定负dt来源与最小修订范围，再决定是否修生产代码或重新设计降落验收。尚未执行该新审计、上游修复或新批次冻结；本批剩余5次不自动重用。结果单独明确范围提交，完整结果SHA写外部进度表。V04不准入V05。
