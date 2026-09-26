# V04 protocol16：按实际目标使用窗口核验导航发布时间

新16001/16002/16003，每个先PID再ESTA X，共最多6次，外部series14。首必需单轮/配对失败停批；不续series13余1、不改判过去失败、不调参、不push/实机/V05。持续授权绑定准确源码/协议/预算，干净源码验证后执行。

仅完整分析链改为height16→handoff16→triplet16：完整保留原始行，全局结构/非递减时间检查；handoff_ready的完整前驱同刻组、窗口内及hover_end结束边界组任意字段不一致即拒绝，其他窗口外未决歧义明确记录、不称已消费/无歧义。没有删行或last-wins。生产Navigator/FlightModeManager及消息源已冻结；原ACK/目标/reset/原始三秒入口/10秒截止和其他话题规则均不变。

项目Iris启动器/模型/world；原位置P、Y/Z速度PID、姿态及全部rate PID；X唯一候选1/0.2/0.4/0.8，2.5m、60秒观察/32秒小激励、固定yaw、完整起降。共同land_speed0.6/down_cap0.55/profile1171；所有安全/性能数值门槛保留。每轮重启及EEPROM完全恢复。

仅IMU播种，PID先行顺序与n=3开发样本限制公开，既有合格配对不混入本批。Z仍仅离线原型，未飞行。执行前capture.py、verify.py、明确源码提交和干净再次verify；原大日志外部存储。
