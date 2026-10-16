# R03 revision01：A 门第 7 轮停批记录

2026-10-16。状态：**needs_revision，R03 未通过**。这是对 [首次失败报告](R03.md) 的新增检查点，不覆盖原报告或历史判定。

## 1. 实际完成范围

飞行源码为 `80c27cb37d889e1b0a70de2124048f6c9075f199`，分支 `research/sta-velocity-regularized`；固件 SHA-256 为 `f5f9f255ed0abdbc728dc4b1ba2ca9eab1c3e03408aa4e0804f9abaf901c0112`。运行前工作区干净，33 个递归子模块版本及内部工作区不变；停止后再次核对一致。

沿用项目 Gazebo Iris 启动器、合格派生软接触模型、`empty_grey.world`、固定参数和 DIV1。新 R-STA 仅开放 X；Y/Z、姿态及角速度保持 PID。没有推进 Z/XY/XYZ、调参、ISTA、R04/R05 或实机。

| 清单 | 计划 | 尝试/起飞 | 已记录完成起降 | 接受 | 失败 | 未执行 |
|---|---:|---:|---:|---:|---:|---:|
| revision01 A：X | 9 | 7 | 6 | 6 | 1 | 2 |
| revision01 B：Z | 9 | 0 | 0 | 0 | 0 | 9 |
| revision01 C：XY | 9 | 0 | 0 | 0 | 0 | 9 |
| revision01 D：XYZ | 9 | 0 | 0 | 0 | 0 | 9 |
| 新矩阵合计 | 36 | 7 | 6 | 6 | 1 | 29 |

另保留旧 `R03/A/batch01/run001` 无效 1 次。因此 R03 累计尝试 **8**、接受 **6**、无效/失败 **2**；总上限仍为 37。第 7 轮已接地但未记录上锁完成，不能算完成起降。没有 A 门 `gate_pass`，不能开放 B。

准确顺序：PID/ESTA/RSTA、种子 71041，均接受；PID/RSTA/ESTA、71042，均接受；PID/71043 失败，原定其后的 ESTA/RSTA 未执行。不能用旧成功日志补齐。

## 2. 资格与真实执行

飞前干净资格 `R03_revision01/A/qualification01/evidence.json`：41 条顶层命令退出 0；475 个不同 C++、1021 个 Python 用例；32768 对旧路径主样本、256 对同 sample 重算；636 项输入指纹及 EEPROM 保持。两种导入顺序的旧失败 ULog 诊断完整通过，但旧失败仍无效。这些是本批飞前的真实测试，不是本次停批后重新执行的测试。

实际启动命令（仅历史记录，不能直接重跑）：

```bash
python3 research/sta-velocity-control/regularized_sta/r03_revision01/runner.py \
  --gate A --execute \
  --source-head 80c27cb37d889e1b0a70de2124048f6c9075f199 \
  --qualification '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision01/A/qualification01/evidence.json'
```

工具会话 41988 最终退出 **1**；原始 `result.json` 于 `2026-10-16T12:09:51Z` 写明 `success=false`、`ValueError('Live ULog transport stale/future')`。启动器退出 0 仅表示进程清理，不是实验通过；清理中的 `px4-shutdown` 返回 255 也已保留在原命令日志。runner 在首败后没有启动 run008。

## 3. 第 7 轮的原因与证据边界

PID/71043 已完成 90.100 秒观察（47.904–138.004 秒）并发出降落命令。失败发生于继承的 `v08/protocol02/monitor.py:104` 降落新鲜度检查，而不是原先的 height/task 导入冲突。

只读前缀复核得到：

- 已读取原 ULog 字节前缀长度/完整消费偏移：104232694；没有遗留半条记录。
- 前缀末尾位置/姿态发布时间：147.344 秒；封口证据 watermark：147.336 秒。
- 随后 CLI 查询实际时刻：147.876 秒；相差 **540 ms**，超过预定 **500 ms** 门槛 40 ms。是过旧，不是 future/时间倒退。
- 当次监视 poll 的宿主耗时为 **532.421744 ms**，此前两次成功检查年龄都为 480 ms。失败行保存的 `now_us=147204000` 是上一轮 landing 对象值，不能当本次真实检查时刻。
- `v08/protocol02/position_live.py` 每次重新解码累计过滤前缀；监视器再检查完整历史，之后才读 CLI 时刻。证据主要支持累计解析/验证延迟侵占新鲜度预算，而不是数据流中断。
- 前缀位置镜像 14534 条，序号 123–14656 无缺口，与原位置逐位对应；最终 ULog `dropouts=[]`、无 corruption。降落期位置/STA 无时间倒退或同刻重复，最大间隔 12 ms，姿态最大间隔 8 ms。
- 末尾仍为 MODE0/AXES0，记录的控制 fault/timing/first_fail/retry/failsafe 为 0，EKF primary0。接地标记为 1，但仍 armed，未记录 `landed_disarmed`。

未记录 read/parse/replay 各子步骤当时耗时，不能精确分离解析、缓冲、宿主调度占比。不能由此断言整机绝无问题，也不能把“可能是监视器延迟”改判为通过。原数值门槛、时间规则及失败保持。

只读审计的 51 个原文件前后指纹不变；按上述精确前缀解码/重算命令退出 0，主代理独立再次执行亦退出 0。它们是同一失败的诊断，不是新增飞行样本或 C++/Python 单测数量。未修订生产控制、监视器、控制 dt、参数、模型或协议。本次没有重新构建/运行单测、MATLAB、补飞，亦未生成九轮独立回放通过凭据。

可复现的只读核心命令如下；实际执行另对 51 个原文件前后 SHA 作断言，未写入原目录。`pending_poll.py:20` 的错误收据使用上一轮 `landing.last_now`，所以必须从本次 CLI 命令记录取 `now`。

```bash
cd /home/yr/Desktop/Codev-autopilot
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH='/home/yr/Desktop/Codev-autopilot/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python' python3 - <<'PY'
import importlib.util, io, json
from pathlib import Path
repo = Path('/home/yr/Desktop/Codev-autopilot')
run = Path('/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision01/A/batch01/run007')
spec = importlib.util.spec_from_file_location('readonly_revision_runner', repo/'research/sta-velocity-control/regularized_sta/r03_revision01/runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
import position_live, position_log, monitor
from pyulog import ULog
assert all(Path(m.__file__).parent == repo/'research/sta-velocity-control/v08/protocol02'
           for m in (position_live, position_log, monitor))
poll = json.loads((run/'landing_pending_poll.jsonl').read_text().splitlines()[-1])
with (run/'log001.ulg').open('rb') as source:
    raw = ULog(io.BytesIO(source.read(poll['raw_offset'])), message_name_filter_list=position_live.TOPICS)
view = position_log.PositionLogView(raw)
evidence = monitor.replay(view, json.loads((run/'height_reference.json').read_text()),
                         frozen=json.loads((run/'task_yaw.json').read_text()), allow_pending=True)
commands = [json.loads(line) for line in (run/'commands.jsonl').read_text().splitlines()]
now = [x for x in commands if x.get('clock') and x['clock']['topic'] == 'vehicle_local_position'][-1]['clock']['timestamp_us']
assert (poll['raw_offset'], evidence['through_us'], now) == (104232694, 147336000, 147876000)
print(evidence['clock09'], now - evidence['through_us'], view.position_log_evidence)
PY
```

本轮检查还执行 `git status --short --branch`、递归 `git submodule status/foreach`、`jq` 收据/均值核对及原始 `sha256sum`，均完成；两次猜测读取路径不存在，随后从 `rg` 的实际路径读取，没有据此修改源码。新增报告的 `git diff --no-index --check /dev/null <报告>` 退出 1 且无诊断，表示新增差异；暂存后的 `git diff --cached --check` 才是提交空白检查。未把这些文档/诊断检查算作飞行通过。

## 4. 前六轮的有限描述性结果

两个完整开发种子块、每算法 **n=2**；不能替代要求的 n=3 或宣称 A 门通过。32 秒主窗内每轴时间加权速度 RMSE，单位 m/s：

| 算法 | X | Y | Z |
|---|---:|---:|---:|
| PID | 0.03654963 | 0.00702332 | 0.00268436 |
| 旧 ESTA（X） | 0.00972766 | 0.00740280 | 0.00255947 |
| R-STA（X） | 0.00814892 | 0.00740939 | 0.00262665 |

12 份 ULog、参数/模式、指标 SHA 和精确恢复已只读核对；4 个已有配对决定各 13 条风险检查独立复算一致。每轮主窗 3200 次更新，实际 h 为 8/12 ms，主窗约束及 mixer 饱和记录为 0。

这里只描述新 R-STA 的 X 跟踪误差较小；Y/Z 没有统一改善，不作显著性或全阶段结论。完整原链分析由逐轮运行器实际执行；本次停批检查没有重新解码前六轮全部 ULog，不能冒称已完成整门独立回放。

## 5. 原始指纹、恢复与预算

数据根：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision01/A/batch01/`。

| 工件 | SHA-256 |
|---|---|
| ledger.json | `3f07de0cbb5e7d2b1480d8c1bff3598c30623e2b41946670d066a65de342f0f1` |
| journal.jsonl | `8811941c20b2a20dcbcd264d41a9ea332a7d922d86dff9265b75f27f34e1e9fe` |
| run007/result.json | `6afe3c3cc80f23e45a8c9c3d728ca86ac84903e0f05cfd71968928b5c3061169` |
| run007/log001.ulg（104628101 字节） | `291fcd380698ead94c728a99599e600d928e268585f44647e097aa77aa59aaa6` |
| run007/12_07_23.ulg（368609 字节） | `36c1920f0b9f6005efb596fcd034158daf372cdabe3939113825dab3228865ab` |

先停止本轮仿真再恢复完整参数。原/恢复 BSON 及实际 EEPROM SHA 均为 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`；ledger 和现场进程检查均无残留模拟器。原失败数据未删。

当前 37 上限减去 8 次已尝试，剩 29；即使全部接受，也只有 6+29=35，不能形成 36 个接受结果。**纯算术下界为总尝试 38（至少 +1）**，但这并不授权拼接不同源码/工具版本。若修复后依现行“同门同冻结版本”规则重新做完整 A9，再 B/C/D27，则需新 36 次、累计 **44（相对现上限 +7）**。具体续接方案尚未冻结或获准，不能把算术下界当可执行预算。

下一步应先离线隔离在线监视开销、补充边界/故障和真实导入链回归，保持完整历史检查与原 500 ms 安全要求；再明确新批是否需要整门重做、种子和准确预算。当前不自动飞行、补样、改阈值或推进后续门。

本检查点仅新增本报告，审查后明确范围提交，完整 SHA 写外部进度；R03 未通过，不作为阶段完成 push。研究自动推进已暂停；用户单独授权的一次额度重置监视仍可保留，不产生飞行权限。
