# AX00 实际检查记录

2026-10-05，工作目录 `/home/yr/Desktop/Codev-autopilot`。以下都是本回合实际执行，不是待执行测试计划。
原始 Git/子模块/编译器命令 stdout/stderr/退出码保存在 `evidence.json.commands`；参数/源文件/种子扫描指纹在同文件。

## 只读审计

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git submodule status --recursive
git submodule foreach --quiet --recursive 'test -z "$(git status --porcelain)"'
git diff 05a8ae3b3c00cf14dd575d87417296baa1996f69 -- src msg Tools sitl ROMFS boards research/sta-velocity-control/v08
python3 research/sta-velocity-control/axis_ablation/ax00/audit.py
```

退出码均0。audit.py 前后两次均0；第二次补充 Z03 实际参数、额外脚本指纹及 EEPROM 只读检查后作为最终 evidence.json。
33 子模块版本/内部状态正常；protected diff 为空；扫描36282份JSON、1个已知空诊断例外，无新非法JSON或候选种子冲突。
audit.py 仅打印 JSON，证据通过文件补丁保存；不运行旧实验入口、不启动PX4、不加载参数。
重跑时 HEAD/工作区会与审计时不同，不能要求整份 JSON 逐字一致；生产/参数/V08源指纹必须一致。

## 实际 C++14 探针

临时目录由 `mktemp -d /tmp/ax00-probe.XXXXXX` 创建（退出0），实际为 `/tmp/ax00-probe.clM17o`。

```bash
g++ -std=c++14 -Wall -Wextra -Werror -I src/modules/mc_pos_control/PositionControl research/sta-velocity-control/axis_ablation/ax00/admission_probe.cpp src/modules/mc_pos_control/PositionControl/StaVelocityControl.cpp src/modules/mc_pos_control/PositionControl/StaVelocityProtection.cpp -o /tmp/ax00-probe.clM17o/admission_probe
/tmp/ax00-probe.clM17o/admission_probe
```

首次编译退出1：探针行33的 int32_t/unsigned 比较触发 `-Werror=sign-compare`；随后调用不存在二进制退出127。
仅在探针比较中增加 `static_cast<int32_t>`，没有修改被链接的生产文件。重编译及运行各退出0。
实际最终 stdout：

```text
mask=0 selector=accept protection=accept effective=0
mask=1 selector=accept protection=accept effective=1
mask=2 selector=reject protection=reject effective=0
mask=3 selector=accept protection=accept effective=3
mask=4 selector=accept protection=accept effective=4
mask=5 selector=reject protection=reject effective=0
mask=6 selector=reject protection=reject effective=0
mask=7 selector=accept protection=accept effective=7
PASS 82 assertions; 8 admission masks; no module/flight
```

82为断言计数，不是82个gtest；覆盖8掩码准入、非法请求保留原effective、armed暂存/取消/disarm、MODE2拒绝，现有1/3/4/7的priming、独立状态、原子提交、同采样不重积分、末轴无效不部分提交、disarm清状态。
不声称该探针测试了整个模块的参数持久化、HTE、起降状态机、dispatcher数值或新2/5/6输出；这些由代码审计标为AX01必需回归。

## 证据与范围复核

```bash
python3 research/sta-velocity-control/axis_ablation/ax00/verify_evidence.py
git diff --check
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
```

`verify_evidence.py` 实际退出0：`PASS 112 evidence checks; no flight or full PX4 regression`。
包括57源文件SHA、3份入口/创建快照一致、V08实际两组参数与选参覆盖项一致、统一候选不变量、种子隔离及EEPROM指纹。
这112项证据检查与82条C++断言分别列出，不合并成194个控制单测。
diff空白检查退出0；最终暂存清单只含两个README、本专项三文档初始及入口快照、四个审计/证据文件、本记录和AX00报告。
源码 `src/msg/Tools/sitl/ROMFS/boards`、V08冻结包无差异；未删除历史数据。

补充文本检查：对research及外部plan的`.py/.sh/.md`搜索带数字/十六进制边界的候选510xx/520xx，排除本专项目录后，命中仅外部专项规划；未将SHA子串或微秒值算作种子。
探索性路径拼错的 `rg`/`sed` 错误及修正已列在报告，不计入成功验收项；组合shell输出最后退出0不能证明之前不存在的路径有效。

## 没有运行

整套历史PX4单测/SITL构建、MATLAB、新/旧ULog回放、任何仿真或飞行、参数写入、新掩码实现、AX01及push。
没有新仿真数据目录，未来48/320轮预算未消耗。本次审计仅限本地证据完整性和现有代码行为，不重新授予旧结果科学优越性。
