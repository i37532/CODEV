# 飞前离线准备记录

2026-10-24，入口 bb56d1414cc0e7e196995f9281a0306ca7f46964，research/ista-velocity-regularized。入口工作区、33个递归子模块干净；本轮生产差异为空。原 EEPROM SHA-256 为 06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。

- 授权：用户明确新9次，历史总上限12次；旧3次不改判、旧未执行6次作废。
- 正式登记：protocol.py --prepare 退出0；74091份JSON，全历史没有结构化种子冲突，原空诊断文件采用已有精确SHA例外。source/doc按非字母数字边界检索，仅发现本轮新增登记文本。初步纯数字检索的6处旧命中均是SHA片段，不是种子。
- 新工具 tools_attempt01：91个真实Python测试，退出0；其中新增8项覆盖StateLimit-only缓存/实际8与12ms/连续HTE/伪造缓存/候选状态误用/严格隐式标志及真实组件接线。不修改旧分析器或历史判决。
- 一次过早预检在prepare尚未结束时因execution.json缺失退出1，未创建证据目录，没有运行测试或飞行；工具对话保留错误。
- preflight01：历史失败夹具CLI限定旧HTE证据目录，新目录被正确拒绝，退出1，保留evidence和日志。修订为本目录独立封装，复用原extract/render函数、原Git及原ULog指纹，输出只写新目录；不改旧工具或旧证据。
- preflight02：107条实际子命令全部退出0，711唯一C++/48目标、912 Python/39套、6个独立oracle、9历史接受完整回放和2失败审计、严格C++14、SITL/Gazebo仅构建均完成。但收尾未生成frozen.json，外层退出1、success=false；不能作为起飞资格。已把冻结清单检查前置，明确先freeze再验证。
- 上述两次预检失败及缺失资格不消耗飞行尝试；当时新尝试/起飞/接受均0。所有外部证据保留在RI04_REVISION01，不覆盖重跑目录。

本协议提交后必须重新取得完整干净源码qualification；本文件不是资格收据。MATLAB未重跑、无实机、未push、未开始RI05。
