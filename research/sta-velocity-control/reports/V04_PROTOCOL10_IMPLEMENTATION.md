# V04 protocol10：降落修复接线及新批次冻结

2026-09-26。起点 `ead33cba094f40dc943736e6ca5c29de81279cfd`，research/sta-velocity-control，主工作区及递归子模块干净。完整读取速度计划、共同规则、进度表和landing10修复/提案。用户“是”有条件批准9901–9903各PID→ESTA X，最多6次，干净提交验证后才能执行。

## 修改与审查

新增版本隔离的protocol10配置/资产、flight12、批次运行器、完整分析器和验证器。未修改src/msg/模型/控制律/dt/参数默认值或安全阈值，未改旧入口和历史判定。新Checks继承已审计的landing10监视器，单独覆盖授权与world来源绑定；非降落检查保持原实现。最终分析在原全部门槛后强制检查原始降落链和完整窗口。flight12相对离线flight11只增加新协议授权门禁，源文本等价测试约束其余代码。

新增13项Python接线测试，覆盖新旧协议隔离、参数逐字节一致、无授权无副作用、种子设计登记精确排除、mock六次/三对及首失败停止和EEPROM恢复、真正完整分析器正例及命令/内环/reset负例。合成正例借历史原始控制数据但只在临时目录/内存替换来源，不是飞行验收。旧八批仍拒绝。

## 提交前实际验证

外部根 `/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04`。

- `python3 -m unittest test_v04_protocol10 -v`：首次13项、1失败、退出1；dry-run所需frozen.json尚未生成，未启动任何仿真。记录于protocol10_targeted01/result.json；完整输出仅工具转录，未伪称有外部原始日志。生成快照后同测试进入全量回归。
- `verify_v04_protocol10.py --output .../protocol10_verify01`：退出0。SITL/测试及DONT_RUN Gazebo构建退出0；109个控制C++与11个真实IMU链C++通过，合计120个不同用例；相同11项sanitizer不重复计数。2048帧原转换合法输入等价通过，原缺陷负对照预期失败/退出1。
- 全部Python347项（原334+新13），25.175s，退出0；两组各2048步速度PID逐样本回归保留。
- 七批clock回放和八批landing回放工具均退出0；新完整入口拒绝八批旧job，284份原输入指纹不变。参数SHA前后 `06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc`，无活动模拟器。
- 295项执行资产冻结；种子登记扫描22979份JSON，无实际复用/非法JSON，既有空M06例外保留。source与firmware最终冻结以干净提交后证据为准，不能用提交前二进制替代。

本报告写入时尚未飞行。未执行MATLAB/Octave、实机、V05或额外调参。先明确范围提交；再在该干净HEAD运行同验证器至protocol10_committed01。外部回执只能绑定通过验证的完整SHA；飞行逐轮同协议，任何必需失败停止。结果单独报告/提交，外部进度表记录两次SHA，不push。完整预算与方法见[协议](../v04/protocol10/README_CN.md)。
