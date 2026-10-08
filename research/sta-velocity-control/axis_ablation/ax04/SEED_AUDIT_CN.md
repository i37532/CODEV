# AX04 种子历史核对

候选正式52001–52020仅用于新AX05；AX04不启动IMU、不生成正式仿真噪声。

1. 开始时复用只读结构化扫描，关闭历史助手的目录排除，扫描仓库research、外部experiments和plan全部JSON。首次38941份、候选匹配0、非法JSON0；唯一既有空诊断按原绝对路径/空内容指纹例外，不作为种子记录。
2. 生成新协议前再次扫描38947份，通过；原始证据保存在seed_audit_initial.json（随后新增AX04离线回归的记录导致数量变化，不是悄悄缩小范围）。
3. 文本检索research/plan里的候选值：命中原专项计划/快照、AX00候选审计和AX03一个非法种子负例。它们未运行该种子的IMU。外部代码命中仅数值常量、NumPy测试/Matplotlib颜色、MAVLink自动字典，非飞行seed分配。
4. `git log --all -G '(^|[^0-9a-f])520(0[1-9]|1[0-9]|20)([^0-9a-f]|$)' -- 'research/**/*.json'` 只命中c5f240fb638fd94669d86c8f9e1c37d7c2efec38的AX00审计：待查重候选列表、candidate_matches=[]，不是运行登记。对历史删除/改名JSON也进行Git内容变更搜索，没发现已执行记录。
5. 新登记只允许seed_reservations.json列出的4个绝对路径及精确SHA：initial audit、execution、manifest和全unattempted outcomes。没有整目录豁免。任何其他attempt/ledger/已修改设计含该种子均冲突；下一阶段正式启动前再次查重。

结构化识别范围为JSON键名含seed的整数/整数列表或数字字符串，以及上述源码/文档补查；不声称能发现未记录或被外部删除且不受Git管理的私下实验。
41001–41020维持V09禁用区，510xx开发种子不再称新种子。V08/formal、旧预算和种子资产完全不变。
