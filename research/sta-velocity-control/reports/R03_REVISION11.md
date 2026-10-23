# R03 revision11：新XYZ门的冻结与资格

入口HEAD17b1a4df1e56ec4de872d087983fdd41497b26af，分支research/sta-velocity-regularized，33递归子模块未变。此次只有独立日志工具/检查接线、测试、版本化协议、计划与报告；生产路径无改动。根因、历史停批和修复分别见R03_REVISION10_STOP.md、R03_POSITION11_OFFLINE.md。

持续授权落实为有限总预算97=历史88+新9，不是无限重复。新D九轮：三算法PID/ESTA/RSTA各三轮，IMU种子71831–71833；先PID，后两算法交替顺序，准确清单见`regularized_sta/r03_revision11/manifest.json`。扫描67061份JSON没有种子冲突，仅四份精确登记SHA豁免；execution SHA9aedae9b6b9de9fdaa79605d2cc1bf7dbbbed026ebac4573d20a054554a35333。初始outcomes全部unattempted。

原revision09 A/X、B/Z、C/XY各9接受/9独立回放/6配对维持原版本；新D另列源码/固件/检查策略版本。不拼旧五轮，不声称同二进制36轮，也不把历史诊断纳入开发验收。127参数、epsilon、TEST8的64秒激励/90秒观察、起降、模型/world/插件、原位置P/姿态/rate PID及DIV1不变；仅Iris SITL。

冻结清单包含865项仓库/派生资产、79外部资产、33子模块，新增完整双时钟链、revision10依赖和三份计划快照。不能用历史资格起飞；先统一离线验证、明确提交，再新干净源码全量资格。运行器默认dry-run，执行必须显式--execute、完整--source-head及准确--qualification。

## 当前验证

统一预提交验证`R03_revision11/D/verification01`实际exit0，101条命令全部exit0，541个不同C++/1935个Python测试；包括32768固定样本对/256同sample重算、旧时钟与监控工具、新94组件及188协议/运行器测试、6旧CLI回放、14份新链历史日志复核和SITL/Gazebo构建。evidence.json SHA-256为20257b88f6d3b5ad8bd97cb22167bcecf41c048e8a06f627e9d7a3252bb5708e。此收据clean=false，不授予飞行资格；仍须新提交后的全量干净资格。未执行MATLAB、新飞行和实机。

离线索引`R03_POSITION11_INDEX.json`列2589份工件的路径、字节和SHA，索引SHA cb0a2be5f4916910068453ab378cc8ca21b31060f91dc7c88f5934c7333c8f50。失败测试、早期诊断、旧失败日志和成功回放均保留；不以最后成功掩盖中间失败。审查确认生产路径无差异、旧冻结文件未动、旧科学计算/风险不等式未改变，新适配仅在明确日志检查接点生效。33子模块及原EEPROM指纹保持。

原数值门槛、配对公式和参数未改变，逐样本回归及旧科学指标等价必须实际通过。首个必需失败停批，保留失败和未执行项。九轮、六配对、九次独立回放全部真实完成才可验收；完整R03后单独结果提交并普通push，不进入R04/R05。

## 复现命令

在仓库根目录配置项目既有依赖后：

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
python3 -B research/sta-velocity-control/regularized_sta/r03_revision11/runner.py --gate D
```

该命令仅列清单。干净资格使用`verify.py --gate D --qualify --output 新外部资格目录`；执行时加上述显式参数，资格证据必须属于当前提交。不能重跑已有batch01或旧revision10清单。验收由`replay.py --gate D --output 新回放目录 --finalize`重新解码和独立配对完成，不手写gate_pass。提交SHA在实际提交后更新外部实时进度，不杜撰报告自身SHA。
