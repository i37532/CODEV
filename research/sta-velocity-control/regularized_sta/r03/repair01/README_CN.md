# R03 离线修复 01：高度工具的同名模块导入冲突

本目录仅作诊断，不改变旧源码、旧失败判定、参数或飞行预算，不产生 `gate_pass` 或新授权。

## 已复现的根因

实际运行器先导入 AX04/AX02，使 AX02 已在 `sys.path` 后部。之后 R02 初始化仅把尚未存在的 V07 路径插到前面，不移动已有 AX02 路径。R03 引入的高度函数来自 AX02，但其内部 `from task import offsets` 到调用时才解析，错误地选中了 V07 的二维 `task.py`，不是 AX02 的三维版本。访问 `p[:, 2]` 因而越界。

独立只读进程已在 R03 A `batch01/run001` 精确复现；原目录全部 62 个文件前后 SHA-256 一致。直接先导入分析器时 AX02 排在前面，所以此前单独组件导入测试没有暴露这一真实顺序差异。这是离线分析接线错误，不能据此判断飞控失稳，也不能跳过未执行的后部检查。

## 修复边界

`adapter.py` 固定原 height、task、analyzer、targets 的 SHA-256。显式按路径加载 AX02 三维参考，不修改 `sys.modules` 的通用模块名。原高度函数 AST 仅将局部导入语句替换为 `pass`，其余检查、时钟、交接及数值阈值保持逐节点一致；`offsets` 通过私有函数 globals 绑定，拒绝二维、NaN 或不合法任务，不填零伪装缺失 Z。

完整分析使用原 `analyze` 的代码对象与私有 globals，只替换高度绑定和诊断输出标记。原日志只读，输出写入新目录；复现所需的原授权/协议文件只是复制，不签发新权限。对外 `accepted` 与 `flight_accepted` 永远为 false，单独用 `diagnostic_checks_complete` 表示修正工具后的检查是否完成。历史失败不改判。

执行入口默认仅离线，无飞行入口：

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH='/home/yr/Desktop/Codev-autopilot/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python' \
python3 adapter.py /绝对路径/原运行目录 --output /绝对路径/全新离线输出目录
```

测试命令及真实失败历史见 `TEST_HISTORY.json`。25 个不同测试通过，包含两种实际导入顺序、伪造二维/抛错 `task` 污染、A/B/C 零 Z 轨迹增量、D 真正 Z 波形、完整高度负例及私有 globals 不污染。
