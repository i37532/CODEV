# V07 最终开发验收包

18次新实验、9组配对、18次独立完整重放全部接受。只使用第七批，不拼历史成功。
飞行源码/协议：6fe452e6088a82a2b432915754f6501ad4023004。
结果提交完整SHA写外部VELOCITY_STA_STATUS_CN.md；本目录不自引用自己的提交SHA。

- `summary.json`：逐轮指标、配对、独立重放argv/退出码/一致性、传感器参数和分组统计。
- `verification.json`：231 C++/503 Python、构建、ULog格式及1431资产实际核验。
- `archive.json`：36份ULog对应的逐轮结果、2106工件索引及副本来源。
- `recording_audit.json`：272436位置副本连续，原latest-value位置话题漏1条但副本保留；无插值/去重。
- `runs`：每轮job/result/metrics、参数、pending轮询与RAM目录证据；大ULog不入库。
- `target_replay.json`：旧六批41份完整任务组件回放，不能替代旧批完整验收或改判失败。
- `tools_snapshot`：外部ROOT实际脚本快照，依赖原ROOT相对路径，不从仓库快照直接执行。

原始日志在`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V07-TARGET`。
RAM原件仍在/dev/shm私有目录；磁盘归档已fsync/源前后及副本SHA验证，不能将RAM当掉电持久记录。
实际100/50/25Hz，XY ESTA+Z PID与全速度PID；rate全部PID。仅功能准入，不是优越性/板级CPU证明。
不重复执行已耗预算，不push、不V08/ISTA/实机。
