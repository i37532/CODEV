# I01：Proper-ISTA 独立离线内核

已完成纯内核与离线验收；**没有新增有效模式，没有接执行器，没有新飞行**。
原 `MODE=0/1/2` 仍分别为原 PID/ESTA/原 ISTA。不要尝试用 mode=3 启动新算法。

- [阶段报告](../../reports/I01.md)、[公式推导/固定测试规格](PROTOCOL_CN.md)。
- 内核：`src/modules/mc_rate_control/StaRateControl/ProperIstaRateControl.hpp/.cpp`。
- GTest：同目录 `ProperIstaRateControlTest.cpp`。
- [结果](results/scalar_summary.json)、[命令/数量/版本证据](results/evidence.json)、[原始数据指纹](results/artifacts.sha256)。

## 与原 ISTA 的区别

新预测变量 `z=s+h*(a-nu_next)`，输出包含 `2*nu_next-nu`；不能套用原 `z=s+h*a` 或原保护重算式。
`z` 不是实际对象下一状态。中间分支 `a=nu-2*s/h`、`nu_next=nu-s/h`，恒定扰动理想平衡点为
`s=0, nu=-d, a=-d`，而原形式为 `s=h*d`。三者的模型/扰动/数值假设见规格。

`evaluate(axis,rate,rate_sp,dt)` 返回不可改写的候选，未推进状态；调用 `candidate.result().valid()`
检查后，`commit(candidate)` 至多提交一次。`update` 是两步的便利封装。丢弃候选不推进状态。
reset/成功设参使同轴旧候选失效；其他轴不受影响。无效结果是 NaN 哨兵，不能发给执行器。
本接口暂不支持“保护改写候选后提交”，保护映射和起飞状态另属 I02。

## 重跑（仓库根，输出路径必须不存在）

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"

python3 research/sta-rate-control/ista_redesign/i01/verify.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I01-replay01' \
  --regression

sha256sum --check --quiet research/sta-rate-control/ista_redesign/i01/results/artifacts.sha256
```

第一条验证会构建/运行新单测、独立二分参考、84 组对象及 sanitizer 重复，回归既有 M09/I00，
构建 SITL 并检查固件符号。不会启动 Gazebo、飞行或写飞控参数。
不加 `--regression` 只运行新内核验证，不能代替本阶段完整验收。
需要项目原有 Python/GTest 依赖及外部 M00 回归 fixture；文件缺失应明确报告，不跳过假称通过。

若只跑 C++：环境同上，`make tests TESTFILTER=ProperIstaRateControl`，必须看到非零测试。
`package_evidence.py` 仅在已完成、明确选定的 attempt 上生成外部原始文件索引，不自动选最佳结果，
输出目录不能位于被索引的数据根内；已提交 results 不覆盖。MATLAB/Octave 本轮未运行。

原始证据：`/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I01`，
包括第一次入口环境失败说明、attempt02 和最终 attempt03；不要在这个已归档目录内补写重跑结果。
