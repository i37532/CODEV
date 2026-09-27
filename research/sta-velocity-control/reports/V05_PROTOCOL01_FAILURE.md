# V05 首批失败与离线修复

2026-09-27，源码 `fad638b592c21c4af57e7be418a4d51ffa1bc145`，原协议种子20001–20003/预算6。
实际仅 run01（PID、20001）执行：起飞、2.5m交接、90.16秒观察和三个激励窗口完成，发送 AUTO_LAND 后调用落地监视器时失败。
`ValueError('Incomplete observation/unsuccessful planned land')`：`v04_landing10.validate_context` 仍硬编码60–62秒；新运行器/基本分析链已经90–92秒，但继承的落地模块未同步。这是本阶段接线遗漏，不据此认定PID失稳。

批次立即停止，0/1接受；没有 ESTA 飞行，后五次未执行，不能补跑。未记录 `landed_disarmed`，不能声称该轮完成起降。
退出时关闭本轮拥有的仿真，参数完整恢复，原始两份ULog均保留：

- `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/V05/paired01/run01/07_38_13.ulg`：`1eedf7f85c940ad37e94bdc396e02d719eed0e6c3343c29262702b9fca0bf283`
- `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260927/V05/paired01/run01/07_38_14.ulg`：`438f2d8ac135ffdfd1cde86a5c93d620d63ec9c3dbb589deed718cffb98ef5e3`

`v05/results01`保存失败账本、运行记录和全部原始工件指纹，不重判通过。

## 离线修复

另建 `v05/protocol02`，保留 protocol01。生产C++、参数、波形、物理安全/性能阈值不变。
新增版本化落地模块，仅将观测时长绑定已规定90–92秒；原未来/过去时间匹配、0.5秒pending、重复命令、reset、状态、故障锁存均保留。
新Y输出全历史检查：缺失/非有限拒绝，Gate后必须为0。在线落地沿用原始ULog的状态关联，不能借异步CLI旧nav_state误判新Gate。
完整激励时钟一致性扩大到全部64秒，禁止Y/XY段时钟跳变；没有放宽规则。
新增21个落地测试（原18个核心场景移植90秒夹具、精确边界/接线/Y负例），并增加Y/XY时钟负例。
冻结新种子21001–21003、每种子PID→XY ESTA、共6次，目录 `V05/paired02`；沿用同一候选、90秒任务及门槛。
用户已明确授权V05持续完成，不再请求普通批次起飞许可。必须在新干净源码提交上通过完整离线验收后执行。

`protocol02/verify.py --output .../V05/offline02` 实际174个C++、421个Python通过（386旧工具+14协议+21落地），各命令退出0；SITL/Gazebo构建、1435字节消息、EEPROM不变检查通过。新协议/修复提交后再验证相同完整集合。
