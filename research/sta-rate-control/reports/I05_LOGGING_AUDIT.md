# I05 执行器日志覆盖离线审计

范围：只读历史ULog，不飞行、不改控制器、消息队列、logger或原批次结果。
起点：research/sta-rate-control，7e8cb0dd84c06c39e9c36243db5958c272781a04，工作区干净。

## 结论

formal03停止条件比此前要求更严格，且与现有日志采集能力不匹配。不能把它解释为ESTA控制失败。
六份旧/新日志中该主题均不完整，匹配样本的三轴力矩及推力逐位一致；这证明已记录部分一致，
不能补全未记录值，更不能证明执行器硬件收到每条消息。

| 日志 | DIV | 悬停回调 | 未匹配执行器记录 | ULog dropout |
|---|---:|---:|---:|---:|
| formal03 ESTA 7001 | 1 | 15063 | 996 | 0 |
| R-B ESTA 6701 | 1 | 15085 | 1082 | 0 |
| R-B Proper 6701 | 1 | 15064 | 1165 | 0 |
| M09 series03 ESTA | 1 | 15054 | 1202 | 0 |
| M09 series03 ESTA | 2 | 15056 | 1457 | 0 |
| M09 series03 ESTA | 4 | 15058 | 1166 | 0 |

独立输出含实际路径、源码SHA、ULog SHA、更新/保持缺样分别计数、时间间隔和logger message_gaps，
见 `ista_redesign/i05_remediation/ACTUATOR_LOG_AUDIT.json`。所有读取的归档日志先校验指纹。
六份记录是目的性诊断样本，不是随机抽样或算法性能统计。

## 源码证据与解释边界

- `msg/actuator_controls.msg`未声明ORB_QUEUE_LENGTH，`platforms/common/uORB/Publication.hpp`
  的DefaultQueueSize默认返回1；`msg/sta_rate_ctrl_status.msg`声明32。
- `platforms/common/uORB/uORBDeviceNode.cpp`的copy对单元素队列读取最新值和最新generation；
  延迟读取会跨过中间发布，对多元素队列则按generation读取保留消息。
- `src/modules/logger/logger.cpp:418`的copy_if_updated记录generation跳跃为message_gaps；
  write_message中的write_dropouts统计写入缓冲故障，两者不是同一种缺样。
- `src/modules/logger/logged_topics.cpp`高频配置确实注册了actuator_controls_0，故没有证据认为
  本轮忘记启用该主题高频日志。高频订阅不保证宿主每次及时读取单元素队列。
- 六份日志logger_status.message_gaps非零，分别最大16692、17207、18208、23970、24975、23084；
  这是所有主题汇总，不得全部归属actuator_controls_0。
- mc_rate_control先发布执行器，再发布研究状态；状态output_valid反映emit。匹配记录一致且
  状态持续更新，与异步logger遗漏单队列中间消息的机制吻合。未记录每主题generation和调度时序，
  因而不能将每个具体缺口的原因或机载消费者行为视为已经直接测量。

## 已实施的修正

增加只读审计工具，区分更新/保持期缺样，检查所有匹配回调的力矩和推力；不插值补样，不把空交集
当等价。主分析器现在在严格断言前输出覆盖数量，使停止原因可审查。formal03冻结的断言仍保留，
原始i05_analysis.json、progress.json和日志未重写或追认为通过。

## 后续可采用的验收方案

推荐在新协议中明确两类证据：完整研究状态序列用于更新时序、积分、保持、TV及频谱；执行器主题
只作有时间戳匹配样本的力矩/推力一致性核对，并逐轮披露覆盖率、间隔和更新/保持分区缺样。
不从这六份已见数据倒推出一个恰好通过的覆盖率门槛。若论文必须证明每次真实执行器发布，
需另行设计SITL专用、带队列的发布证据或日志采集改造及验证，不能简单改变全局执行器队列，
否则可能改变mixer等消费者的延迟语义。

下一步应先冻结修订后的证据要求及剩余17轮的处理规则；现有18轮预算没有完成。
没有依据要求用户直接再增加18轮，也不能现在宣称I05通过或开始I06。

## 验证

`test_actuator_logging.py`覆盖完整记录、更新/保持缺样与窗口、推力不一致和无匹配四种情况；
既有`test_remediation.py`另有五项回归。离线审计读取六个运行的归档ULog，未调用SITL。

实际结果：4/4新增与5/5既有Python测试通过，退出码均0；py_compile与diff检查均退出0。
无需重编固件：本轮仅分析工具、测试、诊断结果及文档变更。
复现需使用项目`.px4-python`及M00 python依赖；将ACTUATOR_LOG_AUDIT.json中的六个rows[].run
作为audit_actuator_logging.py的位置参数，并用`--output`指定不存在的新文件即可；脚本拒绝覆盖。
