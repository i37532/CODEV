# V04 目标交接离线修订

详见[修订报告](../../reports/V04_HANDOFF06_REPAIR.md)。本目录不是已授权飞行协议；新尝试/种子预算均0。

- `protocol.json`：独立新接口契约；原安全/性能门槛不放宽，旧协议不覆盖。
- `ProjectionWireProbe.cpp`：真实ECL投影/MAVLink编解码探针，仅测试使用。
- `evidence.json`：series04真实命令前回放、源码指纹与编码证据，不是新飞行。
- `verification.json` / `python_tools.log`：最终离线109个C++/172个Python结果。
- `artifacts.sha256`：所有外部验证/失败/审计工件指纹。

新脚本仅在`research/sta-velocity-control/scripts/`：`v04_handoff06.py`负责原始目标和单次交接，`run_v04_flight06.py`集成但入口禁用，`analyze_v04_flight06.py`与`analyze_v04_handoff06.py`做独立分析，`test_v04_handoff06.py`补25项测试，`audit_v04_handoff06.py`仅离线留证。旧04/05脚本与历史失败仍可原样复现。
