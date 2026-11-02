# SuperTwisting2.0 原版复现与悬停对比

已按后续请求新增一轮 PID，四系统均完成任务。新版 [速度、位移图及结果说明](/home/yr/Documents/UPSTREAM_STA2_PID_RSTA_RISTA_HOVER_20261102/README_CN.md) 与 [PID 扩展记录](RESULT_PID_CN.md) 单独保存，旧三轮和图片包不变。最新清单为 `manifest04_pid.json`，只授权追加 S304 PID，拒绝重飞前三轮；新增任务已经完成，不应重复执行。以下保留原三系统阶段的复现记录。

本次只比较原版 SuperTwisting2.0、现有 RSTA、现有 RISTA 三套完整系统。各计划一轮：起飞到约 2.5 m，稳定后悬停 10 s，降落并上锁。最多 3 次起飞，原版先行，首个飞行或必需日志检查失败后停止，不补飞、不调参。不是论文正式试验。

已完成三套系统各一轮，全部通过，参数已恢复。结果与两张 XYZ 叠加图见 [简明结果](/home/yr/Documents/UPSTREAM_STA2_RSTA_RISTA_HOVER_20261102/README_CN.md)。以下两次未解锁工具失败保留，不计为飞行样本。

首次 S001 在启动约 1.5 秒时，运行器过早读取尚未发布的姿态话题而停止，未解锁、未发送起飞命令，记录保留。工具增加有界的起飞前话题就绪等待，47 项离线测试通过后冻结 `manifest02.json`；安全阈值、30 秒预热、算法和参数不变。总计允许 1 次已失败启动加 3 次新系统任务，最多仍为 3 次起飞；新任务为 S101/S102/S103。

S101 原版任务随后通过。S102 在解锁前因诊断中的合法“不适用”NaN 无法写入严格 JSON 停止；修正为仅诊断记录使用显式 `NaN` 字符串，控制数值验证不变，49 项测试通过。最终清单为 `manifest03.json`：保留本次已完成的 S101，继续 S202 RSTA、S203 RISTA。总启动上限为 5（含 2 次未解锁工具失败），总起飞仍最多 3；原始两次失败不删除、不改判。

## 原版源码

- 主研究分支：`research/upstream-supertwisting2`，位于 `/home/yr/Desktop/Codev-autopilot`，保留此前未提交内容。
- 原版独立目录：`/home/yr/Desktop/Codev-SuperTwisting2-original`。
- 作者提交：`fc3720f67767c78cfab668777de13f68562fe2fd`，来源 [SuperTwisting2.0](https://github.com/chenshigui542000/PX4-Autopilot/tree/fc3720f67767c78cfab668777de13f68562fe2fd)。独立目录使用 detached HEAD，不覆盖主研究目录。
- 不修改作者控制律、默认增益、估计器和模型模板。编译时由原项目生成 Iris SDF；生成器自行补充 `.gitignore` 的非控制改动单独记录。
- 作者仓库没有可用版本标签，原 CMake 自动使用 `v0.0.0` 元数据；来源以完整 Git SHA 为准，不能将其理解为正式 PX4 0.0.0 发行版。

原版 2.0 的角速度输出由作者 STA 接管；XY 速度误差归一化后仍进入 PID，Z 速度 STA 输出赋值被注释，实际仍是 PID。你的 RSTA/RISTA 则是 XYZ 速度环替换、角速度 PID。因此这里只能比较系统表现，不能声称是只改变速度算法的公平消融。PX4 版本、控制分配及模型接触资产也不同。

## 构建与任务

原版首次构建需要其固定子模块、Python 构建依赖和 Gazebo Classic 开发文件。本机 Gazebo Classic 为 11.10.2；缺少的开发文件放在本次实验目录，没有系统级安装。构建记录保存在外部数据目录。

固件和插件完成并冻结后，手动打开原版 Gazebo：

```bash
cd /home/yr/Desktop/Codev-SuperTwisting2-original
unset HEADLESS DONT_RUN
bash Tools/simulation/gazebo-classic/sitl_run.sh \
  "$PWD/build/px4_sitl_default/bin/px4" none iris none \
  "$PWD" "$PWD/build/px4_sitl_default"
```

不要和自动试验或其他 PX4/Gazebo 实例同时启动。原版 airframe 为 10015；现有 CODEV Iris 为 10016，不能混用参数文件。

自动试验先读取准确清单，不会默认起飞：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python:/home/yr/Desktop/codev doc/experiments/M10-20260917/plot_dependencies01/python${PYTHONPATH:+:$PYTHONPATH}"
python3 -B research/upstream-supertwisting2/tools/run_hover.py \
  --manifest '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-HOVER-20261102/manifest03.json' \
  --job S202
```

`--execute` 才执行，最终顺序为 S101 原版、S202 RSTA、S203 RISTA；工具拒绝已存在的尝试目录以及前轮失败后的继续。不要删除结果目录来绕过限制。每轮参数先备份后精确恢复，使用项目原有底层启动器和冻结固件，不在起飞时重新编译。

目标唯一来源是 PX4 Navigator。CODEV 起飞结束转到 POSCTL 时，发送一次明确 2.5 m 目标的 Reposition 交接，不把中间高度直接锁成悬停目标；不额外发布 Offboard、姿态或角速度目标。新实验关闭已有波形测试 `MPC_VCT_TEST=0`。

## 数据与曲线

外部目录：`/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-HOVER-20261102`。其中保存构建日志、清单、参数、源文件指纹、原始 ULog、任务事件和逐轮结果。三轮均完成且日志有效后，分析器生成速度和位移两张图，每图 XYZ 三个子图，每轴仅三条实测曲线。

```bash
python3 -B research/upstream-supertwisting2/tools/analyze_hover.py \
  --manifest '/home/yr/Desktop/codev doc/experiments/UPSTREAM-STA2-HOVER-20261102/manifest03.json' \
  --output '/home/yr/Documents/UPSTREAM_STA2_RSTA_RISTA_HOVER_20261102'
```

速度为机载估计 `vx/vy/vz`，位移为估计位置相对各自起飞原点；NED 的 Z 向下。按起飞命令对齐时间，不对齐峰值、不拉伸、不平滑。10 秒悬停速度 RMS 相对零速度计算，不冒充相对内部目标的跟踪 RMSE。每系统只有一次，不能作统计显著性或优劣定论；本次未运行实机，也不提交或 push。
