# R03：逐门固定参数开发

状态：准备A门，尚无新飞行；这不是验收报告。
先读 [冻结协议](PROTOCOL_CN.md)、上级 [连续授权](../AUTHORIZATION_CN.md) 和 [R02报告](../../reports/R02.md)。

四门X→Z→XY→XYZ，每门PID/旧ESTA/R-STA各3次，最多36。默认只列清单，不启动模拟器。
生产当前只准MODE3/AXES1，其他新掩码拒绝；后门必须先有前门完整证据和独立源码资格。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 research/sta-velocity-control/regularized_sta/r03/protocol.py --gate A
```

实际运行器只接受准确门、当前干净源码、合格固件/指纹、独立资格路径和唯一外部输出路径；不提供绕过检查的一键试飞。
离线验证使用 `verify.py --gate A --output <全新外部A门目录>`；提交冻结后加 `--qualify` 绑定实际SHA并产生收据。
不把R02/AX04旧资格用于新二进制。失败目录不能覆盖，无限重试或追加预算不属于连续授权。
