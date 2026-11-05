# RI05 准备、检查失败与修订记录

所有记录仅属于本次RI05。旧报告、冻结结果和失败不改判；当前未飞行，不能以离线通过代替资格。

- 入口只读命令核对HEAD/33子模块成功；同时列举不存在的AGENTS.md使组合命令exit2。未发现祖先或目标目录内额外AGENTS规则。
- 只读查找VelocityResearchTask.cpp、VelocityAblationTask.hpp时路径不存在（实际前者是.hpp，后者名为VelocityAxisAblationTask.hpp），组合命令exit2；没有修改生产文件。
- 最初复制旧资格脚本时新ri05目录尚未创建，cp报目标不存在；创建明确研究目录后复制成功，旧文件未覆盖。
- 设计审查纠正任务标识：实际合格R03 C/XY为TEST6、D/XYZ为TEST8，64s；TEST3/4属于另一套直接速度注入，不用于本次飞行。该纠正发生在协议登记/冻结与任何飞行之前，未改变既有任务或数值阈值。
- `A/admission_attempt01` 的 `make tests TESTFILTER=RegularizedIsta -j4` 实际exit2：新增测试中的float直接比较和隐式double提升触发严格编译告警。只修测试表达式，原build.log保留，没有改控制律或门槛。`admission_attempt02` 同命令exit0，7目标207个实际C++用例；较广CTest过滤23目标445个实际用例exit0。两套有重叠，不累计为652；最终飞前仍须统一完整资格。
- 离线源码审查发现复制的回放入口缺少gate参数而调用已传gate；在任何协议冻结/飞行前修复。旧RI04的“当前生产改动为零”测试不适用于本次授权XY准入，必须由RI05明确范围/默认值/历史Git对象检查替代，不修改旧测试或假称旧阶段准入证明仍适用。
- 离线审查指出`pid_calls`是每回调PositionControl::update调用数，不是实际计算PID的轴数。XYZ正常运行仍为1；无闲置PID应以`pid_axes=0`核验。新版HTE分析不能错误筛成`pid_calls=0`而得到空证据，须用非空XYZ正/负例验证。该修订不涉及控制律或数值阈值。
- 读取README时曾误用`README.md`，命令exit2；实际文档为`README_CN.md`，无文件修改。
- 新工具两次预备测试均通过：`tools_attempt01`为88个，增加参数事务/完整回放接线测试后`tools_attempt02`为107个，exit0；另协议22个、冻结12个用例exit0。上述不累加为不同唯一用例，最终完整资格重新实测全部清单。
- `protocol.py --prepare`实际exit0；结构化扫描75212份历史记录，六个新种子无冲突、无新损坏JSON，仅保留既有精确指纹的空M06诊断白名单。注册18轮，当前0尝试，不使用旧飞行补样本。
- `C/preflight01`实际exit1：旧RI04失败样本提取入口只允许旧阶段输出目录，拒绝新的RI05证据路径。RI05增加独立的输出目录包装，仍调用原冻结提取/渲染并逐字核对历史fixture；不改旧脚本、原始日志或旧失败结论。旧冻结清单保留为`results/preflight01_frozen.json`，修订后重新冻结再验；飞行尝试仍为0。
