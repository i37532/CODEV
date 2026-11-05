# V04 protocol14：原始入口通过，导航目标同刻发布检查待接入修订

2026-09-26，**本批failed/needs_revision，V04仍未完成三组配对**。持续授权下执行，不新增人工授权要求；不push、不V05、不实机。Z01离线原型已完成，Z尚未驱动执行器。

## 原批次事实

协议/源码 `e96c170166cabc0eb9e7c50a426a2a572111b3de`，分支research/sta-velocity-control；344项资产，执行SHA `b416bf9d236841744d6688197fdf5ba7c8819ada820383b8f3c0c8a8579a0ebf`。飞前干净源码140项不同C++/366Python（358通用+8协议）及SITL/Gazebo构建通过，退出0。

新14001–14003各PID/ESTA，计划6，实际仅首轮14001 PID。原始三秒入口45.844–48.844s，共301个样本合格；观察48.844–109.324s共60.480秒，32秒激励完成，121.824s降落自动上锁。新raw门控接线生效，没有再次提前宣告三秒。

基础49项检查、V04核心控制/诊断检查通过；最终高度/目标交接链报`Empty/nonmonotonic position_setpoint_triplet`，按冻结规则退出1、其余5停止。不能用启动器PASS替代最终accepted，也不续用原五轮。

固件SHA `3b4fdac267c328423400afc9c95545ef6b235134b6093338bc75255d2789425d`。主ULog84,003,823字节，SHA `9ba1ad8c7f4aab5122bb1a9455f521b2c18d69c2913bf1d287f3356aa0cda7a9`，dropout0/无损坏；降落无IMU削顶、EKF故障、selector/reset、timing异常。RMSE仅诊断：X/Y/Z为0.042979/0.009252/0.002859m/s，不计合格配对。

## 同刻话题为什么不同于采样倒退

`position_setpoint_triplet.msg`只有发布时间，没有timestamp_sample。`Navigator::publish_position_setpoint_triplet()`每次使用`hrt_absolute_time()`，由导航事件更新触发；SITL一个时钟刻度内可重复发布。

这份日志64行中第42/43行（零基）同为121.216s，位于降落期、早已超过观察结束109.324s；全部previous/current/next字段逐位一致，current.type=4。没有负时间差，没有不同目标争抢证据。旧通用data()在选择观察窗口之前拒绝全话题的任意同刻行，于是未进入实际目标检查。

不能简单删除一条记录或把所有话题改为非递减。新增独立[v04_triplet15.py](../scripts/v04_triplet15.py)只读取这一话题：允许同刻的前提是**每个字段逐位相同**，包括NaN载荷、正负零和next/previous；一项不同就拒绝。时间倒退、空/错类型/零时间/字段错位仍拒绝，保留全部64行，不用last-wins掩盖歧义。非同刻话题继续原规则；原日志、原分析器及其失败判定未改。

新增handoff15/height15隔离链只替换上述读取绑定，ACK、命令地址/次数、目标/窗口/坐标/reset/输出匹配及所有数值限制不变；源码等价测试锁定这一范围。不是修改导航/飞控发布逻辑，也不把日志时间语义混同控制dt。

## 实际离线验证

7项新单测通过：正常严格递增、逐位一致同刻保留全行、任意current/next变化、空/倒退/零/错长度、NaN载荷/负零差异、边界不丢行/其他话题仍严格、完整分析链源码差异限定。首版6测试有2个夹具签名错误（未接收get_dataset实例参数），修正后6过、增补源码等价后7过，失败未隐藏。

完整Python脚本回归 **365项实际通过**，命令`python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py' -v`，退出0。结果阶段仅改Python/研究文档，没有重跑C++构建；140C++/366Python是本批飞前实测，不把历史数量重复累计。

两组隔离完整链回放退出0：

- series11四轮候选仍为true/true/true/false，第4轮仍因原三秒高度目标不满足而拒绝，不借新策略掩盖旧错误。
- series12首轮在新单话题策略下完整候选检查通过，但原正式accepted仍false，原metrics与ULog指纹不变。**这是修订分析器的离线证据，不是给历史失败追认。**

原入口适配前一阶段的首个逐字接线测试曾因测试期望字符串把换行写成字面反斜杠n而1/8失败；修正夹具后干净验证全过，没有飞行副作用。实际LandingLiveLog四轮接线回放也保留3/1结论，单独记录而不当额外gtest数量。

## 证据与后续

外部根`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04`，原始series12、protocol14_precommit01/committed01/live_reader01、triplet15_series11_replay01/series12_replay01、triplet15_tests01。仓库保存[结果索引](../v04/results14/ledger.json)、原metrics与独立回放摘要/指纹，大型日志留外部。

EEPROM完全恢复SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无残留仿真。未跑MATLAB/旧七八批全量回放/新Z飞行。共同0.6/0.55降落配置和原算法增益/安全性能门槛未改。

累计16次尝试、3轮接受、1组合格配对；所有13轮未接受保留。下一步将隔离triplet15检查接入新的冻结运行/分析批次，新增准确种子/最多6次预算，提交并在干净源码复核后执行，普通范围不再询问用户。不续原五轮、不追改历史失败；Z02模块接线仍待完成，不把X试飞称作Z验证。
