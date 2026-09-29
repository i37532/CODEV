# V08 第二批完整等额训练

源码0b575f0a6b258eb8e018b57326ca1af0f56d144c；24/24接受，无补飞。PID/ESTA各12次、各3候选×2场景×2种子。
旧training01的13尝试、失败和未执行项仍独立保留，不拼接。

- selection.json：按原定J选择pid2/esta0及独立验证清单，不是正式结论。
- summary/ledger/command/verification：实际源码、命令退出码、逐轮状态，231 C++/533 Python。
- replay.json：24次隔离全链分析退出0；指标值一致，仅counts字典键顺序不同。
- runNN：原结果/参数/模型指纹及metrics小副本。
- original_artifacts.sha256：外部完整原始工件，包括48份启动/主ULog。
- snapshot.sha256：证据副本索引，包含本README；后补selection.json另由Git提交固定。

首次回放replay02的失败也保留。有限的JSON计数顺序比较例外有专门负例测试，不能用它忽略指标差异或改判飞行。
外部数据在`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/training02`。
EEPROM恢复SHA06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留仿真。
V08尚需独立验证、安全先导和正式协议冻结；正式试验未执行。
