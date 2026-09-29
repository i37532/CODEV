# V08独立验证01停止证据

干净源码1321ff43a8e77052f10d98f9c6f8eba194910401；231 C++/544 Python、1751资产及构建通过。
12计划、6实际、5接受、1日志验收失败、6未执行。EEPROM完整恢复，无残留仿真。未补飞、未重选参数。
第6轮已完整起降，但不能按原冻结task.py要求验收，保持failed。

ledger/summary/command/verification及runNN为原证据小副本；12原ULog、348工件的路径/SHA保留。
5接受轮独立全链回放退出0、值一致；failure_audit.json定位单条姿态输出缺失。
task_component_replay.json只是新检查的42个旧任务组件诊断，明确old_verdict不改，不是重新验收旧飞行。
snapshot.sha256仅生成时副本，后补审计/组件回放/失败metrics/README由Git固定。

外部目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/validation01`。
新protocol03b另冻12次独立验证；旧40101–40103不拼入新批，正式留出仍0。
