# R03 revision10 D：第六轮停批，旧判保留

源码17b1a4df1e56ec4de872d087983fdd41497b26af，固件SHA-256 7bc426ed0dda36dabd1ee36a80600dbe5730599e30d74cd678562468c74a7b9b。原干净资格541个不同C++/1653个Python通过属于revision10历史证据，不冒充本次重跑。

新D已尝试6轮、发出6次起飞指令，前5轮完整接受；run033（RSTA、seed71732）在悬停期报`ValueError('Invalid position clock timestamp')`，没有landed_disarmed事件。批次实际exit1，run034–036未执行；不继续该批、不将前五轮填入新门。参数备份与恢复SHA一致、无残留仿真。累计88尝试/86起飞指令/78接受/8失败或无效/2诊断，R03仍未验收。

数据根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision10/D/batch01`。

| 原始文件 | SHA-256 |
|---|---|
| ledger.json | baed1b94a5d0d75272ab788e9f2ffe6420dbeda446c802748b5fe8b89871808c |
| journal.jsonl | 566af65eb9102e964a4251e1ca1ac39924775587c29fe2eb4b62ef4d87784406 |
| run033/log001.ulg（67,354,330字节） | 3024043e2b9f254c729daba196d9d6ba5175f77600e7fbb90acc9447daf6345f |
| run033/09_50_58.ulg（启动日志） | 2f339c599cb3b954d98ef6019f857bf58c99a72e229ba19e3b2880b7330a68ed |
| run033/result.json | 60257098506b72f69732bdf0a26726de05a025f00ee9266d661689f60e220dbc |
| run033/r03_prearm04_timing.jsonl | d111f0f7b188e245109270965de2ae24decc6d56c4b2bb0254390e1052cb7c95 |

五份已接受运行用原分析器独立完整回放，科学指标的JSON数值/类型/数组次序相等、频谱SHA相等，原输入未变。部分回放summary SHA为ca86b7145e2d3d65f90748e3618438302529ba7b0f0bc96a9704422be13f2b88，路径`D/partial_replay01`。这不是D完整门通过。

失败原因在原始完整ULog与67,333,572字节确切在线前缀均可复现：位置有相同发布时间128804000us的两条记录，采样时间分别128796000、128804000us。原话题与排队副本逐位相同、序号连续，无dropout/corruption；未见该时刻的EKF切换/reset/reference改变。旧检查误将publication当唯一采样身份；不能通过删除第一条来修复。

新的审计与限定修复见R03_POSITION11_OFFLINE.md。历史失败保持失败，未完成降落不能离线改判成成功。新有限预算97=历史88+新9，独立XYZ完整门及种子另冻，见R03_REVISION11.md；用户持续授权不取消首败停批、干净源码和完整证据要求。
