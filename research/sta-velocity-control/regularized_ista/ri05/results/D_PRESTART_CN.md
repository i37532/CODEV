# RI05 B/XYZ：执行入口预检失败，零飞行

2026-10-24。状态 `needs_revision / stopped_before_batch`。A/XY 已通过；本文件不把B离线资格当成飞行通过。首次必需有效性检查失败后停止，没有重试或新增预算。

## 实际经过

1. B源码 `6faad54e1ea1041c144d79c97df9475a19b90290` 的 `D/qualification01` 干净资格通过：118命令exit0、751 C++、982 Python、6独立参考；18旧接受回放及2旧失败审计不算本门新样本。
2. `runner.py --gate D` dry-run退出0。代理将其stdout保存到外部 `RI05/D/dry_run01.json`；stdout实际上是JSON加一行说明文字，扩展名选错。
3. 首次显式执行在 `precheck → fresh_seeds` 抛出 `RuntimeError('Seed history scan failed')`，终端会话40376退出1。下列命令及退出码是本轮终端观察的收尾记录，不是伪造的自动ledger或完整原始traceback。
4. 停止后独立只读审计（终端会话70460，exit0）查77929份记录，实际冲突列表为空，唯一无效JSON就是该stdout。四份冻结登记指纹一致；seed没有被飞行消耗。

```sh
cd /home/yr/Desktop/Codev-autopilot
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH='/home/yr/Desktop/Codev-autopilot/.px4-python:/home/yr/Desktop/Codev-autopilot/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python'
export PATH="/home/yr/Desktop/Codev-autopilot/.px4-python/bin:$PATH"
python3 -B research/sta-velocity-control/regularized_ista/ri05/tools/runner.py \
  --gate D --execute \
  --source-head 6faad54e1ea1041c144d79c97df9475a19b90290 \
  --qualification '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI05/D/qualification01/evidence.json'
```

**上面是失败命令的审计记录，不是现在应重跑的操作指令。** 退出1发生在批次目录/EEPROM备份/首轮启动前；入口曾获取并释放共享锁，没有改飞行参数。D没有batch目录、ledger、gate_pass或新飞行ULog。9计划、0尝试/0离地/0接受/0飞行失败、9未执行；另记1次入口拒绝。没有输入数据可供B新飞行独立解码，不能造空ledger通过结果收集器。

## 证据与诊断

- 原stdout保持原路径及全部1805字节，SHA-256 `874270526d0fd015624f187fbb5a2e75af6abd6d0c19e84f55c25aeb53c0a956`。严格JSON解析报 `Extra data: line 98 column 1 (char 1737)`。JSON前缀的9项清单及末行都与原运行器dry-run完全一致。
- 原资格JSON：807016字节，SHA `33c3317c41e68a096a3bdfd65efe0fcca433d7f17796d2dce641270b1a3d3f71`。118个命令日志指纹独立匹配。
- 只读重扫完整输出另存 `RI05_RESULTS/D_PRESTART01/seed_scan.log`（6856字节，SHA `ba8c2b0b38310d5dc62d24a78a75b82611e58a851e8bb37ab3ff35c2a793d015`）。它是JSON内容的日志归档，不新增一份可被历史扫描当成seed使用登记的`.json`；与临时原结果逐字节相同。
- EEPROM仍1129字节，SHA `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，与资格前/后和备份完全相同；33子模块与资格一致；无PX4/Gazebo进程。
- 全部绝对路径、状态及指纹在 [D_prestart_failure.json](D_prestart_failure.json)。原始坏JSON未删除/修正/重命名，审计没有修改历史失败或数值规则。

## 后续最小修订边界（未执行）

这是输出归档错误，不是飞行稳定性、种子碰撞或控制数学问题。可审计的最小处理是明确允许后，将原stdout原字节不变归类为`.log`，登记旧路径/哈希/原因/本次exit1，补齐归档与种子扫描接线负例，重验原登记/干净资格，然后明确恢复原未执行9项的规则。

不能只删末行变成JSON：那会重复出现未豁免的seed字段；也不能扩大目录白名单或全局跳过坏JSON。无需改控制律、参数、模型或放宽验收阈值；未消费的9项不是要求新增9次预算。本次严格停批，没有实施上述修订或再次执行；不push，不RI06，不输出合格XYZ配置。
