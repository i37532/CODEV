# R03 position11：发布时间不是采样身份

## 结论与范围

revision10/run033失败是日志检查把发布时间当作唯一身份造成；并非证据表明控制器采样时间倒退。修复只在独立`regularized_sta/r03_position11`及新revision11运行器/分析链内生效，生产控制律、控制dt、参数、模型、传感器和估计器均不改。旧冻结目录只读，历史失败不改判，离线检查不产生飞行资格。

`EKF2Selector.cpp:417`拒绝重复/倒退sample，`:510`用当前`hrt_absolute_time()`发布；POSIX `drv_hrt.cpp:138`在lockstep下读取当前仿真时钟，不能保证每次publish都推进。`MulticopterPositionControl.cpp:270–276`分别记录publication与sample差，原PID publication-dt的2–40ms约束不改。日志里第二条raw_dt约8ms、used_dt约2ms属这两个现有定义，不把检查修订伪装成控制器dt修复。

## 原始证据

主日志、镜像与在线确切前缀一致：publication 128804000us连续两条，sample 128796000→128804000us；位置log_seq12803→12804，速度publish_seq12803→12804，update_seq12802→12803。xy/z/heading reset计数、ref_timestamp/ref_alt未变，selector未切主EKF。主ULog无dropout/corruption。相同publication还出现在该回调产生的selection、位置/姿态目标等；因此只改位置读取器不足以接通完整验收。

审计工具`r03_position11/audit.py`同时检查完整日志和失败时增量前缀，旧读取器两者仍报原异常；新版只检查可观察到的完整边界，原失败仍无降落完成事件。证据`R03_position11/audit03.json` SHA-256 e1c5b8246cee0418d72fccba7dae5a7b6268427cff60dff0ea25be1d23ca8d1e；67,333,572字节前缀、758282条已解析记录，没有修改原字节。audit01初次只修位置后暴露速度诊断旧严格规则，保留为失败，未改成通过。

## 明确白名单与拒绝条件

| 对象 | 新身份与检查 | 仍拒绝 |
|---|---|---|
| public position及queued镜像 | publication不倒退，sample严格递增；两时钟精确匹配、序号连续、重叠载荷逐位相同 | 重复sample、错配、缺序、内部缺样、载荷差异 |
| sta_velocity_ctrl_status / velocity_ctrl_selection | 连续publish_seq及严格sample，input/publication不倒退，逐记录对齐 | 序号缺失、未来时间、相同sample、错模式/内环/故障 |
| 位置/姿态输出 | 同刻完整组的数量、单发布者记录顺序、全部对应载荷一致；不丢任何行 | 少一行、组内错序、不同载荷、不能唯一对应 |
| yaw目标 | 同刻候选yaw全部相等，保留旧20ms新鲜度；仅统计/安全代理，不冒称真实消费 | 组内不同yaw或无有限值 |
| 其他话题 | 原规则与既有姿态白名单不变 | 不因本修订普遍放宽时间规则 |

在线封口等到位置与姿态都出现更晚publication，再检查完整结束组；开始边界连同完整严格前驱检查。reset、reference、健康、故障及每条隐藏在同刻组内的状态均不省略。原500ms运输新鲜度、40ms位置间隙、下游80%部分覆盖/250ms间隙等阈值不改。镜像/原话题运输尾部可暂未齐，但内部缺失拒绝，封口之前不当完整历史。

主误差权重、真实更新TV、频谱和成本算法不变。位置代理仅在“查询恰好等于歧义publication”时用完整输出组及诊断双时钟对应实际消费；其他记录仍用旧preceding代理，不改称真实加速度。没有通过去重、插值或篡改时间绕过验收。

## 接线与测试

运行器使用私有子类，保留原参数恢复、30秒日志相对预热、计时收据和故障latch；将预解锁、连续监控、降落、交接捕获绑定同一策略。分析器同时绑定height/handoff、R02诊断对齐、位置P/FF目标验证、输出、baseline及姿态yaw检查。每次AST替换要求原结构恰好匹配一次，旧函数全局不被修改；新增结果记录并校验position_clock_binding，独立回放也验证该指纹。

组件四个独立Python进程共94项：policy42、callbacks23、adapter17、recorded12，全部exit0；日志`R03_position11/component_tests01`，summary SHA39dddd7a1a036f678e8ba555cde9372658b808e236f1614488b352c8e38a88f7。包含正例、完整组边界、前驱/reset、重复sample/倒退/溢出/缺样、载荷/顺序歧义、真实失败日志、真实monitor的故障锁存与时序收据；不是94次飞行。

14份已接受历史日志（revision10 D028–032五份、revision09 A001–003/B010–012/C019–021九份）完整新链诊断均exit0；科学指标及频谱与各自原版本逐值一致、原始输入未变。`R03_position11/chain02/summary.json` SHA6ff4ede8fc32f3a5c041642151ad483bbf37f13fd93fa098b770239e54dbf0d3。所有诊断输出标accepted=false，不能填新门；新统一资格将再次逐CLI复核这14份。

测试开发中保留：一次unittest discover通用模块名冲突（测试未实际执行）；首轮协议夹具仍按旧历史批数、旧class MRO及旧绑定身份断言而失败；按新显式依赖更新夹具，生产和科学阈值未改。revision_tests01/02日志不删、不记全通过。原准备过程曾访问失败运行不存在的metrics而失败，已改为只有接受运行要求metrics；原失败仍由result/ULog/账本核验。初次prepare工具会话退出码不可再提取，不补造exit0；成功生成四份精确登记由协议复核证明。

统一实际回归、最终冻结/提交及干净资格见R03_REVISION11.md及对应evidence.json；本报告不预填未完成数量。未执行MATLAB、实机或新飞行。外部证据统一根为`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/`。

复现：配置原项目PYTHONPATH后，以独立进程运行`python3 -B r03_position11/test_*.py`对应每个具体文件（不要把通配符作为一个测试文件）；`audit.py --output 新文件.json`重做失败前缀审计，`diagnostic.py 原接受运行目录 --output 新外部目录`重做完整诊断。工具不覆盖既有输出。
