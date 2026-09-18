# I05 分阶段复现入口

I05-A 只能在 `FROZEN_A.json` 最后修改所在的干净提交运行：

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
python3 research/sta-rate-control/ista_redesign/i05/batch.py --subgate A \
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05/A-formal01'
```

大型 ULog 留在外部目录。A 未通过时不得加入或运行 B/C。

`SEED_HISTORY_AUDIT_A.json` 保存正式飞行前的种子历史审计。`restart.py` 只做两次不解锁冷启动，验证参数保存、MODE=3、AXES=1/3 接受、AXES=7 拒绝和切回 PID，不执行飞行。
