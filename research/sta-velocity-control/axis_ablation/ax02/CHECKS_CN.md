# AX02 检查记录与失败披露

工作目录均为 `/home/yr/Desktop/Codev-autopilot`；起点 `7e352a07a41df65fc56ca25b8a03b30c944bfb53`。
本文件中早期诊断是会话终端记录的摘要，不冒称另存的原始日志。最终完整命令、stdout/stderr、退出码、XML及工件SHA保存在报告链接的外部目录。

## 早期未通过项（未起飞）

1. `make tests TESTFILTER=Velocity -j4`，退出2：缺 `jinja2`。首次调用漏了项目 `.px4-python` 环境；改用已存在的项目依赖，不安装/升级包。
2. 加项目 Python 路径后同命令，退出2：新增测试 `z.v+previous` 触发 `-Werror=double-promotion`。给独立双精度测试的混合表达式加显式 double 转换，不改控制律或容差。
3. 仅 `.px4-python` 路径直接运行新 `run.py`，退出1：缺 `pymavlink`。独立 `axis_ablation/run.sh` 补入项目原 M00 Python 依赖目录；默认dry-run随后退出0。
4. 初版 `test_protocol.py` 实际运行16例，1例失败，退出1：人为把 `control_updated` 从1改为2，旧逻辑 bool转换会吞掉异常。新分析器显式要求update/hold只能0/1；未放宽任何规则。修后16例通过；增加真实模型准备接线测试后17例通过。
5. 冻结工具在 stdin 探查时曾把 `__main__.__file__='<stdin>'` 当源文件，退出1；改为只纳入实际存在的模块文件。此为工具检查，不是飞行/算法验收失败。

以上没有仿真尝试、起飞、种子消耗、参数持久化修改或预算追加。

## 最终复现命令

```bash
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
python3 research/sta-velocity-control/axis_ablation/ax02/verify.py \
  --require-clean --output '<一个新的外部复核目录>'
```

该入口包含：

- 研究分支/HEAD/工作区、33递归子模块、完整种子查重、冻结资产核对。
- 默认dry-run和 AX01/V07/适用V08完整历史回归；PositionControl/ControlMath/Takeoff/RateControl等实际非零用例及SITL/Gazebo `DONT_RUN=1` 构建。
- 新17例协议/运行器/保护分析接线、新12例目标/时间匹配测试、新10例C++波形/独立双精度滞后对象测试；新增实际Run/uORB V任务在历史模块套件内计数，不重复相加。
- 六份旧V08 H日志的只读组件回放，原指标及工件SHA保持，不改判为AX03通过。
- EEPROM前后字节指纹、ULog1475字节格式/队列与元数据检查，受保护路径无差异。

V08旧断言“生产源码自V07完全没变”从AX01起不再适用，仍保留原断言，不计通过、不伪称完整原621全通过。适用历史套件为629 Python；AX02额外29，总658。完整证据内明确给出被排除的唯一断言名称。

## 未执行

新48项全部未尝试。没有飞行、新种子实际输入仿真、真实V任务PID安全门、实机、MATLAB、自动调参、正式消融、AX03或push。
独立对象含两级40/30ms滞后和小恒定扰动，只是离线功能模型，不是Gazebo/实机安全证据。
