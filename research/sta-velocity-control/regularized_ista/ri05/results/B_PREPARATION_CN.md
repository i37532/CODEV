# RI05 B/XYZ 离线准备记录

最终状态：本文件是准备过程的历史记录。其后源码6faad54e1ea1041c144d79c97df9475a19b90290的干净qualification01真实通过，但首次执行入口因dry-run stdout错误归档为JSON而停止；B零飞行、未验收。完整原因与停止边界见 [D_PRESTART_CN.md](D_PRESTART_CN.md)，不能沿用下面历史“下一步”文字自动重试。

A/XY真实9接受、9独立回放、6对78项风险检查通过后，才开始本门。A源码3e633a0d2aba1326d3f79b0033f59787cc479c44，A独立结果de1823566ec6c89cd416252db079d2044f41f905；C/gate_pass及回放摘要e45ce23f6f7996f3306d2202d8c10e9ebea7c13a4cf7f70fa5489c002dec3647作为前门证据。

实际仅七个既定生产/C++测试文件。唯一生产行为：PositionControl中SITL/DIV1 MODE4准入增加AXES7；1/3/4保持，2/5/6拒绝，参数定义/默认值、控制公式、保护、起降、上游、模型及所有RI05 Python/清单/种子/阈值不变。

既有XYZ测试从友元离线override改为真实生产准入，新增16实际C++用例；覆盖三轴参数/nu隔离、一次FF、真实8/12ms、连续HTE只平移Z、实际无闲置PID正常输出、1/4/3/7 armed暂存取消/disarm生效、BSON重启、跨起飞seed、末轴失败和10类异常原子性/锁定/reset。

`D/admission_attempt01/build.log`：`make tests TESTFILTER=RegularizedIsta -j4`首次exit0，7目标223用例。`regression.log`：较广CTest过滤exit0，23目标461用例；两组有重叠，不累计684。新增16已包含，不另计。diff检查exit0。

首次 `freeze.py --gate D --write` 仅设置PYTHONDONTWRITEBYTECODE，未带项目PYTHONPATH；前门回放导入numpy报ModuleNotFoundError，exit1，未创建D冻结清单、未触发飞行。补回项目环境后重跑，不改源码/依赖/阈值，不将该次报错算通过。

必需环境与A一致：`PYTHONPATH=$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python`，PATH前置`.px4-python/bin`。完整本门预检、干净提交资格、9轮飞行及独立回放仍须分别记录；这里不预填通过。

独立审查发现覆盖缺口：首次StateLimit后HTE闭合缓存专项只在AXES4真实生产路径运行，XYZ新增连续HTE测试尚未触及StateLimit。没有发现新的生产控制缺陷；决定在飞行前补AXES7等价测试，不改控制/保护。

因此主动中止`D/preflight01`，外层exit130，记录`KeyboardInterrupt()`，success/approved=false；已完成95条子命令均exit0，749唯一C++、982 Python，但对象/历史回放/最终构建未完整执行，不能算本门资格通过。已明确停止本预检遗留的模型子进程，未停止其他任务。旧D清单移存`results/D_preflight01_frozen.json`，外部全部日志保留；补测试后须新清单、新`preflight02`及干净源码qualification。不涉及试飞消耗或新预算。

补强后`D/admission_attempt02`真实通过：make tests 7目标225用例、较广CTest 23目标463用例，均exit0，两者重叠。新增2项分别走PositionControl正/负扰动和真实Run/uORB，均自然积分到首次Z StateLimit，不手写内部状态；验证strict_axes=3/全轴commit7、HTE只重基Z、下一帧strict7/一次FF、NaN毒化闲置PID，以及后续末轴失败/同sample重算不部分提交。测试源合计比A多18用例，控制逻辑仍只放行AXES7。

build.log SHA `996df4ef48fde02ed9e2347abceccfb6a9aa9138033381cfbe8901f1c608a62d`；regression.log SHA `c2441d5efcabe404f66d4b96199761beda2ff81fb1dc174cde84f1fd158f7aef`。本次补强没有编译/测试失败。

重新冻结D：1085仓库/79外部资产/33递归子模块；工具、127参数、阈值、9轮清单和83101–83103种子保持原协议。

`D/preflight02`完整exit0，118条子命令全0：751唯一C++/48目标、982 Python/41套、6独立参考；102对象轨迹（18数值域停止、6不可行反例分别披露）、18历史接受回放及2类历史失败审计，严格C++14/SITL/Gazebo仅构建通过。它的success=true、approved=false，不用作飞行资格；须在本门明确源码提交后重建并运行干净qualification。
