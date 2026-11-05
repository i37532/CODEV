# V04 protocol17：预解锁因果参考接线

新17001/17002/17003，每个PID后ESTA X，最多6轮，新外部series15。首必需/配对失败停批，不续旧余2、不重判旧失败、不额外调参、不push/实机/V05。持续授权准确绑定源码与执行SHA，先提交后干净复核再飞。

与protocol16相比运行器仅把Checks来源改为v04_monitor17：预解锁取原sealed watermark之前最后完整姿态组，再选不晚于它的真实位置参考，原全量replay通过后建立原LandingLiveLog。姿态前驱/同刻组/新鲜度/reset/安全和后续monitor/landing不变，不允许空窗口、不等待或延长门槛、不伪造时间。

保留triplet16完整目标使用窗口和窗口外未决证据，原三秒raw入口与10秒截止。模型/world/项目启动器、原位置P、Y/Z速度PID、姿态/rate PID、X候选1/0.2/0.4/0.8、2.5m/60秒观察/32秒激励、yaw、完整起降及所有数值门槛不变。共同下降0.6/0.55/profile1171，每轮重启/EEPROM恢复。

只对IMU播种，PID先行与n=3开发样本限制公开；旧配对不混入此批。Z仅离线原型，未接执行器。capture.py→verify.py→明确提交→干净verify.py→授权绑定→run.py --execute；最终真实解码与独立回放，不以构建代替飞行。
