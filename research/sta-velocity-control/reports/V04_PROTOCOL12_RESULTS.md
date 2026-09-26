# V04 protocol12：触地削顶消失，但下降意图参数不一致

2026-09-26，**failed / needs_revision**。协议/源码 `d43ba9043fb060f6b9082a09b0e1a5df641308d9`。原历史10次加本轮合计11次尝试/0接受/ESTA0，不能称V04完成。Z仍离线原型。

## 实际执行

持续授权，12001–12003各PID/ESTA，计划6次。只执行run01 PID/12001，首失败停止、剩余5次不复用。项目Iris启动器/原模型/world，公共下降上限0.5，存储land_speed0.7，日志profile1171。干净提交实际134项C++、355项Python和SITL/Gazebo构建通过。

起飞30.948s，目标交接39.948s，观察48.020–108.648s（60.628s），随后AUTO_LAND。触地后始终未判落地，未上锁；运行到日志超过原128MiB保护，报`Unexpected oversized flight log`，退出1。没有扩大上限、强制上锁或伪造完成事件。固件SHA `9c107d987469884b41612cbbac2fa60c1bb2270a453dfe31a89f1a4bc8b175a3`。

## 原因及责任

高频ULog在降落期 **削顶0、EKF故障0、selector切换/reset0、timing故障0**。慢降在本次避免了之前触地冲击链，但没有完成完整落地语义。

`MulticopterLandDetector::_get_ground_contact_state()`使用存储的`MPC_LAND_SPEED`：只有trajectory vz≥0.9×0.7≈0.63才判为下降意图。本次FlightTask实际发布约0.49999997，因此`in_descend=false`，即使低油门、无垂直/水平运动、已触地，也不会进入ground_contact。最后30秒实录30条land状态全部满足低油门/无运动，但landed/ground_contact/in_descend全为0；目标1500条均约0.5，整个降落满足下降意图的目标样本数0。

上一轮只测试位置控制器内部land_speed被限幅，没有核对独立落地检测器仍读取存储参数，是本次飞前接口审计遗漏，不是ESTA失败，也不是检查器误报。不能通过修改全局land detector、放松reset/日志检查来掩盖。

## 只离线补齐的回归

新增5项真实`MulticopterLandDetector`+uORB功能测试：复现0.7/0.5拒绝、原0.7接触接受、合法0.6/0.55允许接触、精确0.54边界和float邻点、运动/油门/无效测量/NaN及反向目标仍拒绝。不启动异步完整LandDetector/Commander，不称自动上锁端到端通过。源码只增加测试注册，没有修改生产检测函数。

新增真实位置模块测试验证`MPC_LAND_SPEED=0.6`、`MPC_Z_VEL_MAX_DN=0.55`：内部land_speed0.55、存储0.6、输出目标0.55≥0.54，原Z混合测量和PID保留。`make tests TESTFILTER=VelocityModule -j4`退出0；落地5项XML退出0。第一次落地测试夹具遗漏HRT初始化，在析构阻塞，终止自有测试后make退出2；补齐hrt_init后5项通过，不能把首次说成通过。

这组新参数均在项目元数据范围内；FlightTaskAutoMapper给出land_speed，AutoLineSmoothVel与位置模块使用共同下降上限；阈值由原land detector自然计算，未修改其公式。此时只是离线方案，不保证下一次不削顶/一定成功。下一批必须重新冻结新种子/预算/资产、干净回归后再执行，普通范围沿用持续授权。

## 证据

- 外部`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/series10`；[ledger](../v04/results12/ledger.json)、[run01](../v04/results12/run01.json)、[只读audit](../v04/results12/audit.json)、[验证](../v04/results12/verification.json)。
- 主ULog134,661,449字节SHA `b73d52811ce32c5825ba14307f6dc92d68aab523094f70e19c4957b42fd2dc40`；启动222,812字节SHA `a1f709d2abe153b49f99a538bf318f7b4356ff1d42cbdf8a7ca28101b92e3add`。主日志dropout0/无解析损坏，不等于所有话题无丢样。
- [174项原始工件索引](../v04/results12/artifacts.sha256)，含提交前后验证/飞行/只读审计。新增落地测试XML另在protocol12_audit01保存，不追改已经生成的174项索引。
- EEPROM完全恢复SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无残留仿真。未跑完整缺落地窗口的最终验收/配对，不造RMSE排名；MATLAB/旧七八批完整回放未执行。不push、不V05、不实机。
