# V06 协议01失败留档与离线定位

状态：failed/needs_revision，不是V06通过。首批源码4cb91c0d9372039f5c5ccd2a6ea8a7dd9cab2c95；协议d0c864b44a1d76ce0f80fba3db33ae3135245a4a3366f8ca8c29aee8e07182d4。

计划18轮，实际尝试2轮：run01 PID悬停起降、完整日志验收通过；run02 XYZ ESTA起飞后交接前报 Local hold yaw changed，中止并关闭本次自有仿真。没有进入观察窗口，不能算ESTA任务完成；剩余16轮取消、配对0。完整EEPROM恢复，未留仿真进程。总批次退出1，失败result与ULog保持原样。

数据：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260928/V06/series01。仓库v06/results01保留两轮result、指标/配置、ledger、88个原始文件的SHA-256。run02主ULog指纹9db4a3e3cf6975ab1fa056ada725c2bf0c9f3d9c10ba3c26ff789abda654a702。

## 原因

继承的v04_handoff09.capture先由完整原始日志验证起飞正常航向对齐及POSCTL安静窗口，再冻结“新的任务航向”为实测heading。task_yaw同时保留原目标existing_target_yaw。但交接前完整性检查却比较当前原目标与新的实测航向：两个含义不同。

run02在sample39284000us：新指令yaw=1.5633947849273682rad；原目标existing_target_yaw=1.5617005825042725rad；差0.001694202423rad（约0.09707°），超过原目标完整性阈值0.001rad。因此这次停止不能据此归因于ESTA失稳；真正的目标漂移应比较当前原目标和冻结的原目标。新指令相对原目标的有界跳变已有freeze_task_yaw的独立准入检查。

## 修复范围与测试

新版本protocol02/handoff_capture.py仅把该比较的右操作数改为existing_target_yaw；命令param4仍使用原来已准入的实测yaw。保留全部原始日志来源、reset/时钟/主IMU/对齐/1秒安静/新指令跳变/目标新鲜度/位置与高度检查；阈值不变、不改控制律、dt、参数、估计器或起降逻辑。运行器及最终handoff回放都接新模块，历史文件不改。

29个本地协议Python用例实际通过（退出0），包括5个新增测试：原ULog精确复现旧失败；新capture保持原指令与全部来源；伪造freeze拒绝；原目标漂移0.000999/0.001001rad及NaN边界；与旧实现逐文本核对仅一处比较对象和解释注释不同。最初新增fixture属性名run与unittest方法重名导致测试入口退出1，改名folder后29个非零用例通过，未飞行。

此前协议源码复核196 C++/432 Python全通过；本次完整修复后验证另记protocol02证据，不能预称新飞行通过。用户已持续授权普通修复及另冻有限新SITL批次：新24001–24009、新series02、独立18轮、同参数/三任务/安全与性能门槛，旧预算不复用，不push、不进入V07。
