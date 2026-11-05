# V08先导物理模型与时钟核对

以下是离线实现审计，不是先导飞行通过结论。

- `Tools/sitl_gazebo/include/common.h`定义q_ENU_to_NED=(0,.70711,.70711,0)，`gazebo_mavlink_interface.cpp`用它转换WorldLinearVel；因此Gazebo世界ENU的(x,y,z)对应PX4 NED的(y,x,-z)。本插件使用(东,北,0)N。
- Gazebo11 `physics/Link.hh`区分AddForce与AddRelativeForce。插件调用前者，作用于base_link；不使用力矩API。CSV记录每物理步送入AddForce的向量，不是加速度反推的净外力测量，也不包括重力/气动/电机合力。
- 全机质心不等于base_link质心（名义模型约x=.000967742m、z=.000296774m）；施力可能产生绕全机质心的小力矩，保留这种真实耦合。
- `MulticopterPositionControl.cpp`调用excitation.update(local_pos.timestamp_sample,...)；`VelocityDiagnosticExcitation.hpp`用(sample-start)*1e-6−12定义任务时间。故任务零点是timestamp_sample−excitation_time，不是诊断发布时间。
- `simulator_mavlink.cpp::handle_message_hil_sensor`以imu.time_usec设置CLOCK_MONOTONIC；posix drv_hrt.cpp的lockstep分支设置绝对仿真时间。插件simTime与该时钟的数值一致性还必须逐轮实测，不仅凭源码推断。

## 无PX4地面夹具发现的问题

保留ground_probe01–05全部失败/退出记录。前两次使用model://iris，Gazebo实际解析到了已有模型并等待PX4；未启动PX4、未飞行。
改为直接在world嵌入指定Iris后，名义质量审计正确，但mass场景GPS仍加载名义0.015kg而非0.0165kg。
只把GAZEBO_MODEL_PATH前置不足以证明派生include生效。改为GPS绝对目录URI；最初误用绝对SDF文件路径被libsdformat按目录解析，缺GPS，检查正确拒绝。
ground_probe05实际读到7个link，总质量1.55/1.705kg，惯量同步×1.10、质心保持。但SIGINT后GPS组件夹具退出−6，不能把其success字段理解为完整生命周期通过。
ground_probe06尝试只移除model级plugin，GPS实际插件嵌套在sensor下，未移除，退出仍−6；保留失败。
ground_probe07仅物理夹具移除完整GPS sensor及其嵌套插件，名义/增重两模型加载检查和正常退出0均通过。
该夹具与完整飞行模型preflight复核区分；原飞行GPS sensor/plugin全部保留，不修改上游。

该审计不消耗配对开发飞行种子或正式留出；force在这些模型夹具中关闭，未采集控制性能。新的先导仍使用已登记40201–40203。
