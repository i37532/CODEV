# V04 protocol09 / series08：降落监视器混合时刻拒绝

日期：2026-09-26。结论：**failed / needs_revision；V04 未通过，不进入 V05。**

## 1. 授权、实际执行与停止

用户在准确预算申请后回复“确认”。协议/实际飞行源码提交为 `a361ebda9783dc4bf65cbf6e57cce35520b0fa44`，分支 `research/sta-velocity-control`。授权凭证见 [authorization.json](../v04/results09/authorization.json)。冻结清单为种子 9801–9803，各 PID→ESTA X，最多 6 次，首个必需检查失败即停止；不补飞、不调参、不扩大轴、不 push。

实际仅执行 **run01 / 9801 / PID**：起飞、目标交接、60.172 秒观察和完整 32 秒 X 速度激励完成；计划降落初期，在线检查报 `Unexpected excitation fault 2` 并中止，没有完成降落上锁。计划 6 / 尝试 1 / 完整起降 0 / 接受 0 / ESTA 0 / 配对 0；其余 5 次停止，不续跑。八批累计实际尝试 8、接受 0；历史失败不改判。

本轮共两次运行命令调用，但只有一次进入 SITL：

- 04:28:56 UTC：外部执行包装器使用被导入修改后的 `sys.path[:3]` 生成环境，遗漏已有 pymavlink 目录，导入失败，退出 1。没有启动 PX4/Gazebo、创建批次 ledger 或消耗飞行尝试。失败命令、包装器及输出完整保留。
- 修正的仅是独立外部包装器的显式 PYTHONPATH，冻结仓库源码未改；导入探针通过。04:29:45–04:31:41 UTC 真正执行冻结运行器，退出 1；其后的实际飞行失败没有重试。

执行仍由 `./sitl/run.sh --headless --backend gazebo --model iris` 启动。归档进程证据确认 `empty_grey.world`，SYS_AUTOSTART=10016 / Iris，非 DP1000。原位置 P、Y/Z 速度 PID、姿态及全部角速度 PID；日志与参数实测 rate MODE/AXES/DIV=0/0/1、MC_RATT_TEST=0、MC_STA_TKO_MGT=0，速度 MODE/AXES=0/0。

## 2. 只读定位：不同时间的状态被一起判定

下表时间均为 PX4 时间，不是宿主墙钟。

| 证据 | 时间（秒） | 状态 |
|---|---:|---|
| 观察开始 / 结束 | 47.944 / 108.116 | 完整观察 60.172 秒 |
| 在线先查询的 vehicle_status | 107.932 | nav_state=4，仍为 Hold；CLI 显示已有 308ms |
| 原始 vehicle_command | 108.240 | DO_SET_MODE，AUTO_LAND |
| 原始 vehicle_status 新发布 | 108.244 | nav_state=18，AUTO_LAND，armed，无 failsafe |
| 在线随后查询的诊断 | 108.244 | excitation_fault=2，激励输出=0，无控制 fault/failsafe |

运行器以旧的 nav=4 与新的 Gate=2 组合，触发既有分类器拒绝。归档 CLI 输入可精确复现错误；把原始同刻 nav=18 代入同一分类器，得到既有 `expected_planned_landing_gate`，无需改门槛。宿主 `land_command` 事件复用了观察末状态时间，不能当作实际命令发布时间。

这定位了**宿主监视器跨话题观测不同步**，不是 ESTA 飞行失败（本轮尚未运行 ESTA）。相同 ULog 时间戳不能证明控制器实际消费的跨话题先后关系。提前中止也意味着不能证明完整降落安全、不能补写 `landed_disarmed` 或改判接受。已记录区间没有主 EKF/reference 切换或控制故障；没有据此豁免后续降落检查。

## 3. 日志与探索性组件结果

主日志 33,839,787 字节；另有启动日志。两者报告 dropout=0、corruption=false。6017 条观察窗口诊断，实际约 100Hz、最大采样间隔 12ms，内环诊断最大年龄 4ms。32 秒激励内 3200 个样本，X/Y/Z 速度 RMSE 为 **0.045133 / 0.008775 / 0.002025 m/s**；限制占比 0，观察最大倾角约 1.4135°、最大 yaw 误差约 0.000427rad。

上述仅为失败运行的探索性组件证据，**不是完整验收或 PID/ESTA 对比结果**。最终冻结分析器因缺少 `landed_disarmed` 明确拒绝，退出 1；完整降落及完整下游覆盖没有验收。姿态全流 23377 条，独立二进制解析与 pyulog 时间字段一致，LiveLog 的 1049 个字段数组与完整解析一致；本次实际同发布时间数量为 0，因此不能宣称本轮飞行覆盖了“同刻发布”的实际事件。

## 4. 验证命令与真实数量

工作目录为仓库根目录；Python 环境显式包含 `research/sta-velocity-control/scripts`、`.px4-python` 与 `/home/yr/Desktop/codev doc/experiments/M00-20260912/python`。外部基础目录为 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04`，以下 `$V04_DATA` 仅代表该路径。

```bash
python3 research/sta-velocity-control/scripts/run_v04_protocol09.py \
  --source-head a361ebda9783dc4bf65cbf6e57cce35520b0fa44 \
  --output "$V04_DATA/series08" --execute \
  --authorization "$V04_DATA/protocol09_authorization01.json"
# 已执行，退出 1；不要再次执行，预算已停止。

python3 research/sta-velocity-control/scripts/audit_v04_protocol09_result.py \
  "$V04_DATA/series08/run01" --output "$V04_DATA/protocol09_audit01"
# 18 项只读诊断断言通过，退出 0，不是 18 项飞行验收。

python3 research/sta-velocity-control/scripts/analyze_v04_protocol09.py \
  "$V04_DATA/series08/run01" --output "$V04_DATA/protocol09_reanalysis01"
# 退出 1，accepted=false，缺 landed_disarmed。

python3 -m unittest discover -s research/sta-velocity-control/scripts -p 'test_*.py' -v
# 本轮实际 302 项，18.964 秒，OK，退出 0。
```

飞行前已在干净协议提交完成 120 个不同 C++（109 控制 + 11 IMU 转换链）、302 Python、SITL/测试/DONT_RUN Gazebo 构建；另重复 11 项 sanitizer、2048 帧旧源码等价以及预期退出 1 的旧源码负对照，见 [接线报告](V04_PROTOCOL09_IMPLEMENTATION.md) 和外部 `protocol09_committed01`。本轮复核其证据/资产指纹，**没有重新执行 C++ 或构建，不累计为新增测试**。未执行 MATLAB、实机、ESTA 飞行或剩余五轮。

## 5. 可追溯资产、恢复与提交范围

原始文件保存在外部 `series08`；仓库仅保存 [results09 摘要与索引](../v04/results09/artifacts.sha256)，其中 88 份外部工件包含失败命令、实际执行、只读诊断、最终拒绝分析和测试输出。只读诊断前后 44 份原始批次工件指纹一致。

| 资产 | SHA-256 |
|---|---|
| 实际固件 | `651242b1967b67e9c2d68617e52e876e44da7949a0eb67d1ce8f98d62fdd22a2` |
| 主 ULog `04_29_53.ulg` | `d94fd81e9826147b0a84d59042e62e85c8d699692d749626ae0e279215cc00e0` |
| 启动 ULog `04_29_52.ulg` | `401ac8edf859562328a088659f27c65415cf1ca8261abfc48318f4ff81c2cf5e` |
| 执行前后持久参数文件 | `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc` |
| 88 份结果工件索引 | `db1ec93e606e30a0071b6d9df86fb0a58fca812f188b74c5a37d458ee614a636` |

参数已逐字节恢复，所拥有模拟器已停止。结果提交只包含研究诊断脚本、摘要/索引、本文及文档入口；不改生产控制、dt、参数、冻结运行器/检查器、模型或验收门槛。结果 SHA 写入外部实时进度表（避免本文自引用提交 SHA），协议/源码 SHA 与结果提交区分。

提交前再次核验全部 276 项冻结资产及原始/结果/前置验证索引，均一致；递归子模块无改动。一次只读收尾探针未设置上述 PYTHONPATH，资产检查后在导入进程助手时失败；显式补全环境后参数/进程检查退出 0。它不是新飞行或测试通过记录，未修改冻结文件。

## 6. 下一步条件

需另授权**离线修订计划降落阶段跨话题观测/匹配逻辑**，补齐旧 nav/新诊断、逆序、延迟、非计划 Gate、超时及真实故障反例，接通实时和最终分析并回放旧日志。不能简单允许任意 Gate=2、延长所有话题期限或删检查。离线通过后再冻结新源码、种子、顺序和预算，并重新取得飞行授权。本次到结果记录为止，不实施该修订，不复用剩余五轮，不 push、不 V05。
