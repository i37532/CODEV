# I06 前置审计

I06 没有进入训练协议冻结或仿真。计划要求 I05 通过，但 I05-A 的冻结性能门槛失败；当前 Proper-ISTA
只接受 AXES=1/3，AXES=7 仍拒绝，DIV=2/4 也没有 Proper-ISTA 飞行验收。因此无法执行四控制器的
全轴等预算调参，也无法冻结包含 yaw 和分频的公平正式协议。

复核命令：

```bash
cd /home/yr/Desktop/Codev-autopilot
python3 research/sta-rate-control/ista_redesign/i06/check_preconditions.py
```

本目录没有分配新种子、没有产生训练/验证数据，也不是 I07 的可执行冻结点。若用户另行授权，应先建立
I05 remediation 阶段，解决 AXES=3 门槛并依次验证 AXES=7 与 DIV=1/2/4；不能直接修改本记录为通过。
