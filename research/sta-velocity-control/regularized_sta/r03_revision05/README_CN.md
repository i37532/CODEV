# R03 revision05 工具入口

仅本版B/Z→C/XY→D/XYZ，保留旧revision04完整A通过证据。准确范围见PROTOCOL_CN.md和上级AUTHORIZATION_R03_REVISION05_CN.md；总57=历史30+新27，不是自动无限重试。

在仓库根准备现有Python依赖：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1
python3 research/sta-velocity-control/regularized_sta/r03_revision05/runner.py --gate B
```

默认仅预检/清单，不启动飞行。禁止重跑prepare覆盖已登记协议、复用旧batch目录或改判历史。gate A不是本版合法执行项。

维护流程：每门实际非零verify（新输出目录）→freeze→明确源码提交→同门干净verify --qualify→显式runner --execute --source-head 实际SHA --qualification 实际资格路径→replay --finalize→结果提交。前门完整9接受、6配对、9独立回放才可开放下一生产掩码。

分析器历史诊断必须使用--historical-diagnostic和新外部输出目录；输出accepted/flight_accepted始终false，不能用于旧结果改判、新飞行或gate_pass。普通分析只接受本版准确来源/目录/资格。

数值适配只替换旧理想nu候选的固定绝对容差判断，其他AST保持；来源SHA、严格binary32和独立有理数RNE检查均绑定。禁止全局改numpy比较、去重日志、拿applied代ideal或忽略后续检查。

所有新大型数据外置R03_revision05；本目录不保存ULog。每轮参数完整备份/恢复、项目Iris启动器和500ms规则不变。首个必需失败停止，保留失败/未执行项；本工具不自动R04/R05、ISTA、分频或实机。
