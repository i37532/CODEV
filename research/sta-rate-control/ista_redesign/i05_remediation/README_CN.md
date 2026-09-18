# I05 remediation

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
  --output '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RC-formal01'
```
