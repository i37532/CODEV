# Codev PX4 SITL 中文使用说明

本目录是 Codev 定制的 PX4 v1.12.3 工程。已为 Ubuntu 22.04 添加编译兼容补丁，并提供不需要 sudo 的项目内 Python、OpenJDK 11 和 Ant 环境。

Iris 默认使用项目内的 `sitl/worlds/empty_grey.world`：只保留简洁的灰色 `ground_plane`，不叠加花哨的柏油纹理。

Gazebo 的完整启动与操作步骤见 [`GAZEBO_PX4_SITL_CN.md`](GAZEBO_PX4_SITL_CN.md)。

## 一键启动

在终端运行：

```bash
cd /home/yr/Desktop/Codev-autopilot
./sitl/run.sh
```

首次使用时，脚本会自动运行 `sitl/setup.sh` 安装项目内依赖并编译。以后直接执行 `./sitl/run.sh` 即可启动 PX4、Iris 四旋翼和 jMAVSim 图形界面。

无图形界面运行：

```bash
./sitl/run.sh --headless
```

停止仿真时，在 `pxh>` 控制台输入：

```text
shutdown
```

也可以按 `Ctrl+C`。

## 起飞和降落

等待控制台出现下面两行，表示仿真器和 PX4 已准备完成：

```text
Simulator connected on TCP port 4560.
Startup script returned successfully
```

建议先启动 QGroundControl，使其自动连接 UDP 14550，避免无人机在起飞后因无数据链触发 RTL。此电脑已有 QGroundControl：

```bash
/home/yr/下载/QGroundControl.AppImage
```

随后可在 QGroundControl 中起飞，或在 `pxh>` 控制台执行：

```text
commander takeoff
```

降落：

```text
commander mode auto:land
```

查看状态和位置：

```text
commander status
listener vehicle_local_position 1
```

## 使用 Gazebo Classic（可选）

此 PX4 v1.12 分支使用 Gazebo Classic 11，而不是新版 `gz sim`。Gazebo 是系统级依赖，需要你在终端输入 sudo 密码：

```bash
sudo apt update
sudo apt install gazebo libgazebo-dev protobuf-compiler libeigen3-dev libopencv-dev
```

默认关闭非必要的 GStreamer 视频插件，因此基础 Iris 仿真不需要额外的视频开发库。

安装完成后启动：

```bash
./sitl/run.sh --backend gazebo --model iris
```

Gazebo 无界面运行：

```bash
./sitl/run.sh --headless --backend gazebo --model iris
```

## 常用端口

- PX4 与仿真器：TCP `4560`
- QGroundControl：UDP `14550`
- 机载 API：UDP `14540`
- 额外 MAVLink 实例：UDP `14030`、`13280`

飞行日志保存在 `build/px4_sitl_default/tmp/rootfs/log/`。
