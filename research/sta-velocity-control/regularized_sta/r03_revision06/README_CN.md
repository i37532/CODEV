# R03 revision06 工具入口

仅全新D/XYZ九轮，保留A04/B05/C05完整通过证据。总58=历史49+新9；不是旧D续跑或无限重试。详见PROTOCOL_CN.md及上级AUTHORIZATION_R03_REVISION06_CN.md。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1
python3 research/sta-velocity-control/regularized_sta/r03_revision06/runner.py --gate D
```

默认只读预检/清单，不飞。A/B/C不是本版执行门；不重跑prepare，不覆盖登记或既有batch。参数、任务和门槛与旧05 D相同，只有新种子/版本及确定性工具依赖修复。

维护顺序：定向离线回归→`freeze.py --gate D`→明确源码提交→干净 `verify.py --gate D --qualify --output 新资格目录`→显式 `runner.py --gate D --execute --source-head 实际完整SHA --qualification 实际evidence.json`→`replay.py --gate D --output 新回放目录 --finalize`→结果提交。资格与授权均不能用旧版替代。任何必需失败立即停批。

历史诊断使用 `analyzer.py 原run目录 --output 新外部目录 --historical-diagnostic --import-order runner-first`（也测analyzer-first）；输出始终非授权，不能改变旧accepted或生成门通过。数字候选审计与height→handoff→三维任务依赖均用私有固定来源绑定，旧目录全部只读。

`revision_audit.py`仅输出范围/历史来源摘要，不构建、不授予资格。原始ULog留在外部R03_revision06，仓库保存路径/指纹/结果摘要。实际达到完整D9/6配对/9独立回放，且原ABC证据保持，才可报告R03通过；不自动R04/R05、ISTA、分频或实机。
