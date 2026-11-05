# R03 prearm04：日志预热路径离线修复

2026-10-19。**日志准备路径的离线修复与回归通过；没有新增飞行，R03 仍未验收**。
不继续旧 run008，不改判任何历史失败，不扩展到 B/C/D、R04/R05。

## 1. 基线与问题

入口：`research/sta-velocity-regularized`，HEAD
`0126e0b8cd56f56da56c47be56a00f6bd2c9e0fe`；工作区起始干净。
33 个递归子模块正常、无仿真进程，约65 GiB磁盘可用。
EEPROM SHA-256 为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`。

revision03 的第7轮PID在解锁前报 `Stale prearm ULog`，不是空中控制失稳。
当时 reader 虽已改为增量解析，却在 ready 后才首次建立，预热期间仍不消费日志。
15次历史尝试各有29次warmup；revision03的203条warmup计时中，reader记录均为空。

复核保存的原 reference 与随后 CLI 位置时间，revision03前6轮年龄分别为
**468、500、488、460、440、500 ms**；两轮已恰好达到500ms上限。
失败第7轮原reference/字节截断没有保存，其精确age仍未知。
此前505.502ms的周围CLI宿主间隔不是精确解码时间，也不能拿最终归档重建原在线age。

累计仍为15尝试、14实际起飞、12接受、3失败/无效。当前36项清单只接受6项，
失败1项，余29项未执行；旧接受不拼成新门。

## 2. 实际修改

新组件独立放在 `regularized_sta/r03_prearm04/`，旧冻结版本一字未改。

- `integration.py`：在原warmup监视之后建立并持续消费同一个owned日志reader；
  decoder、所有历史和未完整尾保留。prearm只再读取一次捕获的文件末端，不循环追赶。
- 缺文件/首部未完整仅为准备态，不能准入；文件身份变更、截断、损坏、dropout等锁存。
  没有成功预热读取、重复start、原安全检查失败，都继续拒绝。
- 原reference选择、之后取CLI当前时间、`0 <= age <= 500000 us`及完整replay顺序保持。
  不前移now、不删历史、不全局替换旧模块；位置镜像、reset、同刻姿态歧义规则保持。
- 成功和失败均在finally留下文件身份、增量字节/offset/pending、reference/watermark、
  实际CLI时间、分段耗时与错误收据。NaN只在JSON证据层显式标为无效数值，不修改判定输入。
- `verify.py`：默认只展示离线计划；执行时独立校验旧43条命令白名单，并追加3份新测试。
  新收据所有执行/飞行/资格字段均false，不调用旧verifier的授权入口。
- `replay.py`及三份测试：生命周期、原500ms边界、完整历史负例、合成前缀与独立解码对照。

没有修改生产控制律、controller dt、PID/ESTA/RSTA参数、epsilon、传感器/估计器、
模型、land detector、日志数值安全阈值或任何旧飞行清单。
本组件尚未接入可启动的新批次，不把离线类工厂当已激活的执行器。

## 3. 旧日志回放

方法在执行前固定于 [离线协议](../regularized_sta/r03_prearm04/OFFLINE_PROTOCOL_CN.md)
和脚本docstring：用435个已记录warmup时间选取原ULog连续物理字节前缀，明确为
**合成增长截断**，不是历史writer实际长度；不重排、去重或拼接消息。

`replay01`实际退出0：15主日志、435个warmup前缀，加60个重复/partial-header/
partial-body/补足探针和15个最终EOF，共510次新旧增量对照。
每文件首warmup、末warmup和最终EOF另用旧full-pyulog reader独立对照，共45次。
15份完整归档一致，914项输入首尾SHA保持；14个已保存原age保持，第7轮未知age仍未知。

510次位置镜像对照均成功；reference和sealed_time各465次成功、45次相同IndexError拒绝，
原因是每文件最早3个合成warmup前缀尚无姿态证据。这些准备期拒绝没有被计为prearm准入。
增量比较471,217,181个字段值，独立冷对照121,164,950个字段值；重复前缀有重复值，
这些数字不是独立试验样本量。

逐前缀范围是原字段位模式、完整位置镜像、reference_row及sealed_time结果或相同拒绝；
不是逐前缀执行整套飞行heading/landing验收。完整prearm与历史故障规则另由接线/对抗测试、
旧监视器回归和完整分析链检查覆盖，不能混称历史失败现已通过。

15次首warmup冷读最大36.843ms；420次后续增量读取最大22.017ms。
最终整个归档大尾追赶为0.007915–1.732758s，单列，不计作正常在线暖读取。
读取耗时不包含全部CLI、校验、写盘和调度；静态归档/cache测试不证明在线时延或WCET。

## 4. 实际测试与命令

分项：接线26项、独立对抗27项、回放工具22项均退出0，共75个不同新测试。
早先23/25项接线开发运行及重复27项对抗不再累计；没有为了通过而改500ms阈值。
统一入口 `verify.py --execute --output .../verification01` 实际退出0，46条顶层命令全部退出0：
**475个不同C++用例、1218个Python用例**，包含上述75个新测试，不能再重复相加。
旧路径32768主样本对与256同sample重算通过；两种导入顺序的真实旧完整分析链一致，
旧失败仍拒绝；SITL及`DONT_RUN=1` Gazebo仅构建通过。
688项输入指纹、33个子模块及EEPROM前后一致；消息格式1475/708字节、队列均8保持。

回归沿用既有明确排除：V08原生产文件hash不变断言不适用于已建立的研究分支；
R02“所有新模式仍关闭”及其对应两项审计不适用于已冻结R03的A门开放。
原R02历史证据保留，本次独立核实仍仅MODE3/AXES1在SITL开放，没有新增开放路径。
不是声称这些不适用断言本次通过。

入口默认计划、严格白名单/路径边界检查退出0；3项输出替换边界和4项注入/授权漂移检查
均拒绝不合法计划，属于工具审查，不再加到1218的unittest计数中。
本次最终回归与历史回放无非零退出；早先分项重复运行保留但不增加独立用例数。

复现环境与入口（输出目录必须全新，不覆盖旧收据）：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
python3 research/sta-velocity-control/regularized_sta/r03_prearm04/verify.py --check-plan
python3 research/sta-velocity-control/regularized_sta/r03_prearm04/verify.py --execute --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_PREARM04-20261019/verification02'
python3 research/sta-velocity-control/regularized_sta/r03_prearm04/replay.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_PREARM04-20261019/replay02'
```

这里`verify.py --execute`只运行离线测试/构建，不执行飞行。上面02目录是未来复现示例，
本轮实际使用`verification01`、`replay01`，不能把未执行的示例目录当证据。
新verifier严格匹配旧收据SHA与独立命令白名单，拒绝shell注入、去掉DONT_RUN、
追加授权命令、未声明的输出路径替换或旧收据漂移；没有继承旧收据的飞行权限字段。

MATLAB、真实在线新prearm、任何新飞行、参数写入、seed登记、实机、R03后续门及R04/R05未执行。

## 5. 证据与历史保留

外部根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_PREARM04-20261019/`。
`replay01/evidence.json` SHA-256：
`636d21bc60785b5b6fc8bfd0ab9a4ec521128310eca54f672681e739bb080276`。
`verification01/evidence.json` SHA-256：
`3ec2e71cd007d0175104f79d92d7a1a91772017e52eebea7266363328e9e4156`。
对应逐命令输出、XML、实际计数及完整生成物指纹位于该目录和`artifacts.sha256`。
本次离线构建固件SHA为 `d3e5319ddb4df25919b99531fd53f47451753811a4acde00ea05a1a7fc1a27cf`，
不是旧飞行固件，也不是后续新批次干净提交的飞行资格。

旧三批账本SHA不变：

| 账本 | SHA-256 |
|---|---|
| 原R03 | ce05b50487bc7f2ee39fa607df648f7919613ee8b856b9c9b1073bdbdd331fd8 |
| revision01 | 3f07de0cbb5e7d2b1480d8c1bff3598c30623e2b41946670d066a65de342f0f1 |
| revision03 | 7a1661e09418341803272f1b156cc9d75aeaca41cfbb59353d674c6772dca8dd |

三份append-only journal也保持；15份主日志字节数/SHA与result登记一致、15次参数恢复保持。
没有删除失败数据、改判、补飞或生成新的flight ledger/gate_pass/authorization。

## 6. 下一批之前还缺什么

候选方案为**R03总上限51＝历史15＋新36**，较44增加7；仍按A9→B9→C9→D9。
这只是预算缺口提案，尚未授权、登记新种子或生成新manifest。
只增加1次无法在同门同源码的规则下重新完成A门；历史6个接受不能拼入修复后门。

下一步需要明确新预算及执行意图，冻结新种子/顺序/36项清单；把本组件接入独立新版运行器
和分析指纹链，完成干净源码提交、固件构建与新资格核验，然后现场预检再启动A门。
原首败停止、不补飞、不改阈值或参数的规则保持。R04/R05不自动开始。

本轮提交SHA将在提交后记入外部实时进度，不预填自身SHA；未push。
独立审查核对了实现、回放与报告。回归后仅澄清离线协议中的“禁用--execute”是指
飞行运行器，不禁止`verify.py --execute`离线测试；执行代码及全部旧冻结文件保持测试版本。
