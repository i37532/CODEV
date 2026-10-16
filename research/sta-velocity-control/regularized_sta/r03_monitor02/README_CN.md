# R03 在线监视器离线修复 revision02

仅修复宿主日志读取的重复解析开销。生产控制、参数、模型、控制周期、旧判定及 500000 us 新鲜度门槛均不变；本目录不能起飞。

## 修复范围

旧 `PositionLiveLog` 在每次轮询中重新解析累计 ULog 前缀。新 `incremental.py` 只解码追加的完整记录，保留半帧直到下次，所有已选话题的原始行、顺序和位模式仍保留。每次返回不可写、不会随下次追加变化的快照。

只优化解码，不增量裁剪安全检查：原 `PositionLogView`、航向、reset、降落的完整历史检查照常运行。不去重、不丢弃故障、不提前查询 now、不将当前时刻伪装成旧时刻。坏帧、掉包、未知 ID、订阅替换/删除、文件截断/替换等锁存拒绝；当前支持固定 schema、追加式 ULog，不支持的日志变化直接停止。

依赖固定本地 `pyulog/core.py` SHA-256 `130187f7676dd53582f984085a8659f6a2c0545fb627c7a683e7609807a6f2ef`；升级依赖必须重新资格验证。

`integration.make_checks` 只为新运行器派生类替换 `start_heading` 的 reader 导入，其余 AST 和旧模块 globals 不动。记录 `r03_monitor_timing.jsonl`，区分宿主 poll、read/decode/snapshot 时间和实际 CLI 时间戳；该文件不是飞行验收的替代品。

## 离线运行

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest discover -s research/sta-velocity-control/regularized_sta/r03_monitor02 -p 'test_*.py' -v
```

单测包含 48 项解码/回放统计与 35 项真实类接线/时间边界检查，实际数量以执行输出为准。真实回放入口为本目录 `replay.py --output <新的外部目录>`，拒绝覆盖已有收据；不启动 PX4/Gazebo、不修改旧日志或原判。

回放原 R03 一轮和 revision01 七轮的 16 份 ULog：全部选择话题逐字段比较 dtype、shape 和原始 bytes；实际轮询边界及合成大块边界使用原完整检查，结果或拒绝原因必须一致。报告中未使用字段的 NaN 用浮点位模式编码，仅用于 JSON 报表，不进入任何判定。

性能另用独立 reader，严格按原 landing_pending_poll 行顺序推进，重复 offset 也保留。首轮累计追赶单列冷读，其余每次真实 poll 均纳入；预定暖轮询 `decode + 完整位置/航向/降落检查 <250ms` 是本机离线余量，不含 CLI、完整在线写盘和调度，不是 WCET，也不保证未来飞行不会停批。10/25/50/75% 大块追赶耗时另外保留，不能冒充实时 poll。

旧 run007 使用记录的 now=147876000、watermark=147336000，仍是 540ms，仍失败。离线新读取更快不能改判旧运行。

## 新批次边界

配套 `../r03_revision02` 冻结历史 8 次＋新 36 次＝R03 上限 44；新清单目前全 unattempted，执行权限全 false。只有干净源码离线回归通过不代表 R03 通过，也不代表允许自动飞行。详见修复报告与新协议。
