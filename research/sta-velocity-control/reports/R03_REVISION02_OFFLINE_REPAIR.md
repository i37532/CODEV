# R03 revision02：监视器离线修复与批次预算修订

2026-10-16。结论：监视器增量读取及旧日志回放通过；本轮零飞行，R03 仍未验收。仅修复工具并冻结新预算，不继续旧 run008、不开始新批次或 R04/R05。

## 1. 范围与原因

入口分支 `research/sta-velocity-regularized`，HEAD `1ae44ba4b1a8039412125584e9783d04559550eb`，开工工作区干净，33 个递归子模块及其内部工作区保持。沿用 Iris Gazebo Classic SITL 限定；没有改生产控制、dt、参数、传感器、模型、估计器或 land detector，也没有部署实机。

revision01 第 7 轮在降落期间失败，已接地但未记录自动上锁：读取水位 147336000 us，随后实际 CLI 时间 147876000 us，年龄 540 ms，超过原 500 ms 门槛。该轮监视耗时 532.42 ms，旧读取器每次重复解析累计约 104 MB 日志，证据支持宿主监视延迟侵占新鲜度预算。不能据此认定 IMU 中断了 540 ms，也不能把旧运行改判通过。详见 [原停批报告](R03_REVISION01_STOP.md)。

## 2. 实际修复

- 新 `regularized_sta/r03_monitor02/incremental.py` 只解码追加的完整 ULog 记录，半帧等待后续；保留全部已选话题的历史行、顺序、重复/倒退时间和值的位模式。快照不会因后续追加变化。
- 原位置镜像、航向/reset、降落完整历史判据保持，不去重、不截掉历史故障，不提前取 now，也不改 500000 us 门槛。格式/订阅异常、掉包、文件替换/截断等拒绝并锁存；固定 schema 之外的变化不静默兼容。
- 新 reader 通过独立派生类接入，继承 `start_heading` 仅移除原 reader 导入，其他 AST 不变；不修改旧模块 globals。增加实际 CLI 时间和 read/decode/snapshot/整次监视耗时记录。
- 固定 pyulog 实现 SHA `130187f7676dd53582f984085a8659f6a2c0545fb627c7a683e7609807a6f2ef`，依赖不同即拒绝。
- 新 `r03_revision02` 明确绑定两批历史与 44 次总预算，保持完整参数/场景/门槛及分析算法。执行、单轮入口、接受/门验收均拒绝本轮未开启的飞行；离线资格收据必须 `approved=false`。

旧 R01/R02/R03/revision01 文件及所有生产路径相对入口 HEAD 无变化。原失败数据和前六次接受结果保持，后者仅作开发记录，不拼接新矩阵。

## 3. 真实回放与性能边界

外部证据根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/`。

`R03_monitor02/replay03/evidence.json`：命令退出 0，8 次历史运行的 16 份 ULog 全部解码；选定话题共 56,629,671 个字段值逐 dtype/shape/bytes 一致。203 个实际/合成前缀边界经原位置、航向及降落全历史检查，结果或拒绝原因与旧读取器一致。491 个原文件首尾 SHA 不变。该回放不签发 gate_pass，也不改历史接受率。

性能使用另一个独立 reader，按原 landing_pending_poll 的全部行顺序执行；重复 offset 不省略，首次累计追赶单列冷读，随后 155 次真实相邻 poll 全部纳入，未筛除慢样本。

| 历史运行 | 暖 poll 数 | 最大解码＋完整检查耗时 |
|---|---:|---:|
| 原 R03 run001 | 16 | 50.97 ms |
| revision01 run001 | 20 | 49.39 ms |
| revision01 run002 | 21 | 57.43 ms |
| revision01 run003 | 20 | 63.27 ms |
| revision01 run004 | 21 | 66.03 ms |
| revision01 run005 | 21 | 51.66 ms |
| revision01 run006 | 21 | 57.14 ms |
| revision01 run007 | 15 | 52.70 ms |

均满足预定 **250 ms 离线余量检查**；不是改变在线 500 ms 门槛。该计时不含 CLI、完整在线文件写入/调度，不是 WCET 或未来全阶段飞行通过保证。首次冷读及 10/25/50/75% 大块追赶耗时另保留，不冒充实时 poll。并行离线回归与桌面进程可能影响宿主计时，不解释为飞控板 CPU 性能。

旧 run007 用原 now 重新核对仍为 **540000 us，accepted=false**。修复后的速度不能倒推旧运行通过。

## 4. 修订预算与准确清单

| 项目 | 尝试预算/实际 |
|---|---:|
| 原 R03 已尝试 | 1，无效 |
| revision01 已尝试 | 7，6 接受＋1 失败 |
| revision02 新 A：X | 9，种子 71101–71103 |
| 新 B：Z | 9，种子 71111–71113 |
| 新 C：XY | 9，种子 71121–71123 |
| 新 D：XYZ | 9，种子 71131–71133 |
| R03 总上限 | **44＝历史8＋新36**，相比37增加7 |
| R04 / R05 | 54 / 200，未变、未开始 |
| 专项总预算 | 298；不是本轮可直接执行次数 |

每门 PID/旧 ESTA/R-STA 各 3 次，PID 先行，之后旧/新次序按冻结清单交替；A 全门通过后才准 B。新的 36 项 outcomes 全为 unattempted，本轮实际尝试/起飞/接受 **0/0/0**。

初查 56,914 份历史 JSON 无新种子冲突，注册后 56,919 份复查通过；只豁免四份准确指纹的新登记文件，不豁免整个目录。完整 127 项参数、任务、波形、窗口、阈值和原顺序保持；不重新调参、不要求新算法胜出。两批旧 ledger/journal、恢复收据、接受指标严格绑定。

新清单并非只补一轮：同一新版本重新完成 A9，再 B/C/D 各9，不能把旧6成功和新结果拼成一门。首个必需检查失败仍停批，不自动补飞、换种子、追加候选或放宽门槛。

## 5. 测试、失败记录与命令

分项实际执行：协议 51、运行器 39、分析器 31、门回放 33、范围审计 13；解码/回放统计 48、真实类接线/时间边界 35；全部最终退出 0。独立审查确认保留原完整判据与时间规则。后面的统一回归会重复运行这些测试，不能把分项数再加到统一数量上。

提交前完整回归 `R03_revision02/A/offline_verify01` 已通过：**43 条顶层命令均退出 0，475 个不同 C++、1125 个 Python 测试**；32768 对原 PID/ESTA 路径主样本及256对同 sample 重算一致。SITL及 Gazebo `DONT_RUN=1` 构建退出0，两个真实导入顺序的原失败日志全链诊断一致，原 accepted 仍 false。660项输入指纹、33子模块和 EEPROM 保持。此时工作区含待提交新文件，`clean=false`，因此这是提交前验证，不冒称干净源码资格。

提交前 EEPROM SHA 为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；固件 SHA `14f136feeea1314543a096f5a79b497aa23908e9152376e78fe4e598102213ee` 只属于本次提交前构建，后续干净提交重建应另记，不混用。

本轮保留的开发失败（均不是新飞行）：

1. `replay01` 退出 1：旧检查返回值包含未使用字段 NaN，报表禁止非有限 JSON 导致序列化失败。现仅在报表层编码精确浮点位模式，不改监视输入；补齐不同 NaN payload、正负零、无穷测试。
2. `replay02` 退出 1：误将一次性 10/25/50/75% 大块追赶列为暖 poll，最大 745.10 ms。203 个前缀等价及16日志/原文件检查均通过，但错误性能口径不算通过。保留收据；在重跑前改成独立 reader 的实际相邻 poll 口径，250 ms 数值不变，不排除任何真实慢 poll。
3. 分项编制期间发现 JSON 中 2.0/2 类型不一致、mock 路径类型及禁止飞行说明排除项错误，修复后严格类型测试通过；首次接线测试使用缺 pyulog 的环境在收集前退出 1，改用冻结 M00 依赖后真实执行。没有把这些失败隐藏或计为飞行尝试。
4. 暂存审查 `git diff --cached --check` 退出2：四份新协议/登记文件末尾多余空行。仅移除空行，同步新登记和未提交冻结快照的指纹；参数和清单内容未改变。最终干净资格应使用该格式修正后的提交，不把此前660项旧指纹冒称最终版本。

可复现命令（输出目录须新建，不能覆盖已有收据）：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest discover -s research/sta-velocity-control/regularized_sta/r03_monitor02 -p 'test_*.py' -v
python3 research/sta-velocity-control/regularized_sta/r03_monitor02/replay.py --output '<全新外部回放目录>'
python3 research/sta-velocity-control/regularized_sta/r03_revision02/verify.py --gate A --output '<R03_revision02/A下全新验证目录>'
python3 research/sta-velocity-control/regularized_sta/r03_revision02/runner.py --gate A
```

最后一条仅 dry-run。`--execute` 当前必定拒绝，不能把离线通过收据用作飞行权限。

| 外部工件 | SHA-256 |
|---|---|
| replay01/evidence.json | `7cff4dfc0fae3433152b5c807e53868b16027a3649e4e5d2ea046444d3094dbe` |
| replay02/evidence.json | `999103f92a6f024fdb539fc66f9a6210d3388119baa3a36850a8210e0cd9f9b8` |
| replay03/evidence.json | `ed8d1695ef09d95ccd8da87c1816bd579ae9bd2665dc5d983df09e1e4fe42d71` |
| 新 execution.json | `6705fc12d7e5960dee2e28b64c4ab3f31d88c61c33278381600098999a82ecad` |
| offline_verify01/evidence.json | `74f7c242c0d9a79a7bfe4195700d02b481ecbab34cd414062ee06e0aa62d98a8` |

## 6. 交付与下一批前置

新增独立修复目录、revision02 协议/工具、授权边界说明、三份新的计划快照及本报告；外部 TODO/PROMPTS/STATUS 同步预算。旧快照不覆盖。明确范围审查和真实提交后将完整 SHA 写入外部进度，不预写本报告自身 SHA。

下一批仍缺：明确启动新36次清单的执行意图、对应可执行版本及干净源码/固件资格、飞前进程/容量/参数/模型/插件/种子现场核验。当前只有 A 的既有生产准入，B/C/D 还要按各门前置逐步开放与资格验证。新监视链的完整在线有效性仍需下一批实际飞行证实。

未执行 MATLAB、新飞行、参数写入、Z/XY/XYZ 扩展、R04/R05、ISTA 或实机。本阶段未通过，因此不 push，也不恢复自动研究飞行。
