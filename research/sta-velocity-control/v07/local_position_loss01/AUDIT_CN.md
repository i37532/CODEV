# V07 第二批：真实位置日志缺样审计

2026-09-29。仅离线，不改变控制、估计器、参数、uORB队列、logger或验收门槛。源码9f10dd0cca69c8c3da11fdafd1a966138cb5f307上的protocol02第二批首败停止。

## 已证实的事实

第9轮PID/DIV2/seed29005，观察期间失败，未完成计划降落。主ULog为外部VELOCITY-STA-20260929/V07/series02/run09/02_24_43.ulg，69415933字节，SHA256 `e4cba3c3a8d43a8095614ae240317c2100b6b079daf42207bfaf645f7acc3d3c`。

- 控制诊断publish_seq=9853、update_seq=9852，input_timestamp与timestamp_sample均为99316000μs。
- **完整文件**的vehicle_local_position中不存在该发布时间；相邻记录为99304000、99324000μs。sample也对应这两条。后续数据已写入，不是在线前缀尚未齐全。
- 原在线检查和完整ULog的同一heading replay均拒绝`Missing consumed local position sample`；没有插值、最近邻代替、跳过或重新判为成功。
- ULog损坏=false、dropouts为空；logger_status的dropouts也是0，而总message_gaps在98.632–99.632s从50617增至51119。后者是所有订阅的累计统计，**不能把这502次都归因于位置话题**。
- 全原始运行工件读前/读后SHA相同，`audit.py`退出0仅表示诊断完成，flight_accepted仍false。

## 为什么没有dropout也能缺话题消息

本版本`EKF2Selector.hpp`用普通`uORB::Publication<vehicle_local_position_s>`；消息没有ORB_QUEUE_LENGTH，因此`Publication.hpp`的DefaultQueueSize取1。`uORBDeviceNode.cpp:155–185`在queue=1时复制最新载荷、直接前移订阅generation；`write:252–254`下一次发布可覆盖唯一存储。

控制模块与logger独立订阅。控制模块读取A后，logger尚未读A时发布B，后者可能只读取B。logger的high_rate profile已经将此话题设为interval=0，这表示不限速，不代表无损保存。`logger.cpp:418–440`把跳代记为_message_gaps；`:1064–1085`的写入dropout是另一条统计链。不能通过只增加文件缓冲区或只等待ULog刷新证明解决。

实际uORB离线用例，复用既有初始化夹具，未启动仿真或异步飞行：

1. `LatestValueSubscriberCanMissConsumedPosition`：相同生产位置话题，两个订阅者；控制订阅者获取99316000，日志角色延后读取只得99324000、generation跳2，再读已无更新。
2. `PromptSubscriberRetainsEachPosition`：每次发布后读取可保留三条准确时钟。

2个不同C++ gtest通过；编译、链接、运行全部退出0。这里只证明该机制可发生，并结合完整文件缺失定位到记录链；没有现场调度追踪，不伪称还原了第9轮精确线程时序。未直接运行完整logger线程。

## 当前决定与下一步

本批9尝试/8接受/1失败/余9取消。DIV1 6/6和3对通过，DIV2仅首对通过；DIV4未启动。既有IMU同刻发布问题已离线修订，新失败不是IMU白名单误判。历史原判不变，不拼接不同批次凑满验收。

按用户“除非系统原因”的停止条件记录为**系统日志证据链blocked**，而不是控制器失稳、依赖未安装或V07通过。当前完整证据契约无法由原latest-value日志传输保证；继续不修改记录链而重复飞行，只是在赌调度。这也不说明每轮必然丢样。

恢复前应单独实现并验证**不改变控制消费者语义的日志完整性方案**：优先专用、带原输入时钟/序号的消费快照与丢样检测，或隔离的记录通道。不能直接把共享vehicle_local_position全局队列调大：所有订阅者会受到读队列语义变化影响，需要额外审计。必须验证突发/延迟读取/溢出负例、控制dt及输出等价、格式长度/带宽，再冻结准确新源码和有限批次。不得以允许缺必需输入、删失败轮、提高阈值或重复种子代替修复。当前未擅自实现这个上游传输改造。

复现（环境同V07报告，输出须新目录）：

```bash
python3 research/sta-velocity-control/v07/local_position_loss01/verify.py --output /tmp/v07-position-loss-new
python3 research/sta-velocity-control/v07/local_position_loss01/audit.py --run '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V07/series02/run09' --output /tmp/v07-position-audit-new
```

未运行新批、MATLAB、实机、ISTA、V08。参数精确恢复，无残留仿真进程。
