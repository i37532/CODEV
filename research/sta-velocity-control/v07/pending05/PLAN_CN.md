# V07 降落pending的有界即时取证

用户持续授权修复日志链到V07通过。第四批源码d37a4cb3ed4e8351acc0ab027dd4149dd1bc1eb2，结果d267bb8aaa0b875ff503dedb3e1170e5b8e2da89：5尝试/4接受/1降落监视超时/13取消，不改判、不补飞。文件命名和位置独立队列在该批均完整。

## 原因与边界

失败初次landing poll的CLI Gate已为2，raw前缀水位139176000，当前139516000；次次水位139636000、当前140016000。两个now正差500000μs，不能解释为仿真超出>500000；旧validator在重算证据前触发宿主>0.5秒。完整ULog有command139176000、AUTO_LAND139180000及后续Gate，不能因此改判当时在线及时。

原PositionLiveLog每次重解累计prefix；同机离线warm解码约0.29秒，加CLI/全历史检查/普通循环0.1s睡眠会挤占pending期限。原日志没记录每个host读入时刻，不能把离线成本当本次精确调度轨迹。新增audit.py保留原SHA、实测成本、记录水位，并清楚标注从原数据切出的前缀/0.35秒快速调度是**合成情景**；不是重建精确历史字节到达或给失败翻案。

## 最小实现与原限制

新protocol05仅包装landing阶段的监视调用：若pending，立即再次调用完整旧父级监视，不先返回普通飞行循环睡眠。每次仍做BaseChecks内环/位置/倾角、选择器、原始位置完整性、完整历史航向/reset/健康及降落关联。额外poll重读机载CLI position/status/land，没有控制或仿真命令。

原landing.py、position_live.py、position_log.py、flight.py、core.py、cadence.py、analyze.py保持字节相同；**两个500ms期限、raw/CLI年龄、所有阈值不改，pending_since不重置**。解析和检查所花的时间仍计入原期限；机器过慢仍须失败，不宣称任意宿主都可保证时限。最多8次立即poll防止两时钟都停的异常无限循环，普通时钟会更早触发原0.5秒上限。写landing_pending_poll.jsonl记录每次前后host时间、now/sample关联、pending起点、结果/错误、原始字节和offset。

8项新增Python使用实际原LandingMonitor验证即时解析成功、旧慢轮询仍超时、无pending不重复、未决不能重置期限、真故障传播、未来状态拒绝、冻结时钟有限次数、运行器接线/原validator字节相同。继承全部原测试和4项实际logger C++探针；预计226 C++/479 Python，最终以实际evidence为准。新的调度不减少检查，也不只取最终状态掩盖中间故障。

## 全新有限批次

protocol05：新33001–33003 DIV1、33004–33006 DIV2、33007–33009 DIV4，每种子PID→XY ESTA，各3配对、全18次。旧四批接受轮不拼接作新批通过；原失败和未用预算不续跑。种子历史核对后先源码/协议提交、干净完整复核再执行；前门不通过不推进，首败仍停止并诊断。

外部V07-LIVEPOLL/series05；保持原90–92s观察/64s固定yaw低速8字、2.5m、合格Iris软接触和启动器、XY ESTA+Z速度PID、全部rate PID、增益、滤波、数值门槛与分频顺序。没有调参、ISTA、硬件、V08或push授权。

完批后独立重放、检查所有pending实测时限、36份预期ULog及指纹、参数恢复与差异审查，独立结果提交并写报告/外部进度完整SHA；没有证据不能称V07通过。
