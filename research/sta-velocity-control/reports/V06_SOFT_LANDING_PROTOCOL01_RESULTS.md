# V06-SL protocol01：一轮接受，第二轮缺日志结束边界

2026-09-28；飞行源码5bee3023d0dab41489ec896b6307688e954c062c。计划6轮、实际2轮，PID接受1，XYZ ESTA完整起降但最终数据验收失败1，余4取消，完整配对0。本专项/V06均未通过，不补飞、不改判旧失败。

干净源码实际196 C++/454 Python、SITL/Gazebo构建和619冻结资产全部通过，命令退出0。源码/参数/协议在本批飞行期间未修改。新接触模型只改变base碰撞参数，不改任何生产控制/估计器/land detector、默认参数或数值验收条件。

## 本批实际结果

- run01 PID/25001：起飞30.984s，观察48.944–139.016s，147.936s落地上锁；最终接受。三IMU无clipping、六EKF无fault，selector保持0；sensor_accel实例1/2峰值Z约63.329m/s²，IMU0约55.426。独立新目录回放退出0，metrics逐字一致。
- run02 XYZ ESTA/25001：起飞30.968s，观察48.900–139.628s，149.600s落地上锁。原V00、XYZ内核/任务与降落链检查通过；新增landing_health报 `Missing health boundaries`，故最终拒绝。飞行运行器success=true不等于整轮accepted=true；批运行器退出1。
- 原始selector最后记录149.220s，早于结束边界149.600s；全部6个estimator_status记录到149.932–149.940s，三个sensor_accel和vehicle_imu到149.944s。因此缺口来自低频selector的后边界，而非已证实新IMU截幅/控制失稳。不能据最后已知状态外推、不能删掉边界要求。

模型两方相同，仍.6/.55下降，rate0/0/DIV1及旧激励关闭。没有比较完成三对，更不能宣称软接触解决所有工况或ESTA性能胜出。

## 保留与修复方向

外部根 `VELOCITY-STA-20260928/V06/soft_landing`：series01、batch01.log、authorization01.json、verification_committed01、replay01/run01。仓库小证据见v06/soft_landing/results01，原始ULog与所有指纹保留。EEPROM逐字恢复06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留仿真。

下一步普通离线修复：在原落地上锁事件之后、停止logger之前增加只读尾段收集；所有必需健康话题至少具有结束边界记录且原严格检查通过，才可完成记录。收集时必须仍落地上锁，限定等待15秒墙钟；等待不是通过，故障/缺样/超时仍失败。原飞行窗口和数值门槛不变。旧protocol01入口/判定不改，新入口/测试/协议版本与新种子另冻结，在持续授权范围内继续，不复用旧余量。

此结果提交只记录失败，不push，不进入V07/实机。结果SHA提交后写外部进度。
