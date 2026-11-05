# I05 remediation

最新：日志规范及剩余17轮安排见 [RC_CONTINUATION_LOGGING_V1_CN.md](RC_CONTINUATION_LOGGING_V1_CN.md)，
逐轮清单见 [RC_CONTINUATION_LEDGER.json](RC_CONTINUATION_LEDGER.json)。
`continue_rc.py`现提供清单检查、离线首轮重分析和显式续跑三个入口。下面旧batch命令是历史复现入口，不能用于直接续跑17轮。

新入口（仓库需干净；先设置下文PYTHONPATH/PATH）：

```bash
python3 research/sta-rate-control/ista_redesign/i05_remediation/continue_rc.py
# 仅离线，目录必须不存在：
python3 research/sta-rate-control/ista_redesign/i05_remediation/continue_rc.py \
  --assess-first '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RC-first-amended01'
# 此命令会实际启动17轮预算，首轮重分析必须先成功：
python3 research/sta-rate-control/ista_redesign/i05_remediation/continue_rc.py --execute \
  --first-assessment '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RC-first-amended01'
```

运行时把当前干净HEAD、构建后固件SHA、原轮源码/固件、原清单指纹写入新目录binding.json；
清单中的空HEAD占位不替代运行绑定。首轮重分析后只允许追加reports目录的结果记录，否则需重新离线分析。
已有输出目录拒绝复用。失败停止，不自动重试；第0轮永不加入飞行清单。

原 I05-A 结果保持 failed。本目录按 R-A→R-B→R-C 新子门推进，当前只冻结 R-A；后续文件只有前门
通过后才能加入。大型日志写入外部唯一目录，不覆盖 I05。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
python3 research/sta-rate-control/ista_redesign/i05_remediation/batch.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RA-formal01'
python3 research/sta-rate-control/ista_redesign/i05_remediation/batch_rb.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RB-formal01'
python3 research/sta-rate-control/ista_redesign/i05_remediation/batch_rc.py \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RC-formal02'
```
