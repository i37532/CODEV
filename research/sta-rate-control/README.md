# PX4 STA 研究目录

当前仅 M00：原 PID 基线。没有接入 ESTA/ISTA，也没有实施 M01。

- `plan/`：M00 开始时三份外部计划的历史快照。
- `environment.md`：环境、模型、参数与启动约定。
- `baseline/`：版本指纹、参数和指标摘要；不存大型日志。
- `reports/M00.md`：验收、失败记录、限制及下一步边界。
- `scripts/`：SITL 捕获、ULog 分析及证据索引生成器。

## 复跑一轮（仅本机 Gazebo SITL）

先阅读 environment.md，检查没有其他仿真、QGC 或实机链路。沿用当前冻结的 Iris 参数；不要导入 DP1000 参数，也不要使用全局 param reset。原始 EEPROM/导出 BSON 和 ULog 参数快照保存在每次运行目录，复跑前应核对与基线参数是否一致；若参数不同，输出不能直接当同配置对照。

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 -m pip install --target '/home/yr/Desktop/codev doc/experiments/M00-20260912/python' -r research/sta-rate-control/requirements-m00.txt
export PYTHONPATH='/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
python3 research/sta-rate-control/scripts/run_m00.py --output '/home/yr/Desktop/codev doc/experiments/M00-replay-01'
python3 research/sta-rate-control/scripts/analyze_m00.py '/home/yr/Desktop/codev doc/experiments/M00-replay-01'
```

已安装上述固定依赖时跳过安装。输出目录必须不存在；每一轮单独启动/退出，不覆盖历史。先按 environment.md 编译固件。脚本失败退出非零并保留日志；只限仿真，失败清理可能终止空中的模拟实例，不具备实机安全降落保障。

运行器保存本次子进程 PID、源码 SHA、二进制 SHA、运行器 SHA、跟踪文件补丁、CLI 返回码、阶段时间、参数和仅本次新增的 ULog。分析器独立核查 ULog 哈希和状态。指标时间窗为记录的 hover_start 至 hover_end，设定值使用最后已发布值对齐；不同话题频率不同，不能视为同步全速测量。

## 数据归档与版本规则

本次原始数据根目录为 `/home/yr/Desktop/codev doc/experiments/M00-20260912`。`build/` 是构建/单测原始输出；`runNN/` 是成功或失败试验的控制台、命令、ULog、参数、指标。所有失败都保留，报告同时说明调试尝试总数和冻结场景的重复次数。Python 依赖缓存不作为实验数据提交。

提交只包含研究目录的小型文本和 JSON；`baseline/artifacts.sha256` 索引外部证据。Git 克隆本身不含大型 ULog，迁移/共享论文数据时必须另行复制并校验原始数据；本阶段没有上传。脚本 `capture_m00_provenance.py` 是本次一次性现场采集工具，不要在新 HEAD 上覆盖历史 provenance。外部状态表后续变化不会改变历史计划快照的含义。
