# R03 revision09 入口

新36轮四门复验，累计90次上限。先阅读PROTOCOL_CN.md。默认只显示当前门清单：

```sh
python3 -B research/sta-velocity-control/regularized_sta/r03_revision09/runner.py --gate A
```

只有新干净源码资格通过后才使用 `--execute --source-head 完整SHA --qualification 外部资格路径`。B/C/D必须分别拥有前门9接受、6配对和9独立回放。所有36轮保持相同源码及固件，结果留外部后统一提交。

独立回放：`replay.py --gate A --output 外部R03_revision09/A/replay01 --finalize`，后续门同理。不能用旧ABC或两轮UP08诊断填充本版样本。科学、保护和时钟数值标准承接原协议；不自动扩展试验。
