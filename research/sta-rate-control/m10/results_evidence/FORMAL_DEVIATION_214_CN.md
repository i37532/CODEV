# 第 214 轮用户授权的协议偏离

用户明确授权：“允许第 214 轮也保持无效、不补飞，记录新的协议偏离后继续剩余 386 次”。原始 `FORMAL_BLOCKER_214_CN.md` 保留为历史诊断。

第 214 轮 `0213_A_m1_inertia_s3103` 仍是数据质量无效：飞行期及主指标窗口内丢样，共缺 1817 条诊断，不能接受 TV/PSD 等完整指标，不能证明丢失区间无故障。不补飞、不改旧分析或执行记录，不增加种子数；从第 215 轮继续原 600 次清单。

冻结的 batch_m10.py 只接受单条解锁前缺样或已经修复的分析。两者都不适用于本轮，因此 adjudication 明确写 `retained_prearm_gap=false`、`analysis_resolved_without_reflight=false`、`accepted=false`。没有假称其满足原续跑规则。

为实施本次授权，外部 `resume_authorized_214.py` 在内存中仅扩展 batch 的“已暂停任务续跑判断”，限于精确的批次路径、轮次、授权文字和原始指纹；新增许可标志为 `user_authorized_inflight_data_loss`。它先核对原 batch SHA，再沿用完整原 main 和 execute 流程，包括冻结提交/清洁工作区、固件插件一致性、全 600 任务清单及后续异常停止规则。脚本包含非目标轮次/路径拒绝自检。

这是公开记录的编排流程偏离，而非声称编排完全未变。仓库文件、控制器固件、插件、参数、倍速、原始日志、分析窗口和有效性门槛不变；不授予未来新阻塞通用放行权。

复现此次续跑（仅本机原路径、冻结提交和原始证据）：

```bash
cd /home/yr/Desktop/Codev-autopilot
PYTHONPATH='.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python' \
python3 '/home/yr/Desktop/codev doc/experiments/M10-20260917/resume_authorized_214.py'
```

正式报告需列出第 101、214 轮两次独立授权、真实有效样本/配对数和所有失败，不能写成 600 次全部有效。外部适配脚本和授权记录随最终原始证据索引保存。
