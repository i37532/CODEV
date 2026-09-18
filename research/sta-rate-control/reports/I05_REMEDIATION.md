# I05 remediation 阶段报告

日期：2026-09-18

分支：`research/sta-rate-control`

结论：**R-A 与 R-B 通过；R-C 的首批 18 次因 divisor 被 runner 覆盖而整批无效。remediation 尚未完成，等待是否授权全新的 18 次 R-C；I06 仍 blocked。**

## 1. R-A：pitch 诊断与重新准入

旧 I05-A 的唯一失败 seed6301 中，Proper pitch RMSE `.0052889` 实际低于同 seed ESTA `.0054648`；
失败来自与更安静的跨 seed ESTA 中位数比较。旧日志无 fault、饱和、状态串扰、映射或标定漂移，因此
没有改 gain/g，而是冻结新的同 seed 配对非劣规则。原 I05-A 仍保持 failed，没有追认。

协议提交 `821af583c6deb7d0dd867d01d8755eb323e23755`。新种子6601–6605，ESTA/Proper各5次；
10/10 单轮有效、5/5配对通过，pitch主窗口配对比值中位数 `1.0147432`（门槛1.10），无 violations。
最大倾角1.9066°、最大高度误差.1181m、ULog dropout 0。

外部目录 `/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RA-formal01`，463文件、
354371438字节；summary SHA-256 `2b098dfebcd37b4ae806a963d340d038b8827b03b57c447783991667d4e0940e`。

## 2. R-B：AXES=7

源码/协议提交 `cae1396d16050fbd3914d19fbb57b6f21234cdb6`，runner修复提交
`49138d2e8d3fc54385b556ccf1f918b8557498d2`。Proper MODE3 首次开放 AXES7，沿用独立 yaw 标定、
旧保护和原四元数 world-z→body yaw 映射；全轴正常路径不计算闲置 PID。

`RB-formal01` 在飞行前被旧 R-A 静态门禁拒绝，0 次飞行，完整保留。修复后 `RB-formal02` 使用
种子6701–6703：ESTA/Proper各3次，6/6 单轮有效、3/3配对通过，三轴窗口汇总比值中位数
`.9988353`（门槛1.10），无 violations。最大倾角1.8058°、最大高度误差.1621m、dropout 0。

有效外部目录 `/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RB-formal02`，279文件、
211224453字节；summary SHA-256 `5caebdbe54ad1cc2d961b0fb90da78978fa07720bc68aa44363669cd597e7eaa`。

## 3. R-C：DIV1/2/4 无效批次

协议/源码提交 `a444a96496c3195e591cd4b8f8d49c5b560fe1ac`。冻结计划是 DIV1/2/4 各 ESTA/Proper×3，
共18次。飞行均完成且没有安全失败，但事后审计发现 18份 `m04_config.json` 的 `MC_RTC_DIV` 全部为1：
继承的 M10 nominal scenario 在 job 参数加载后再次设置 DIV1。分析器从实际配置读到1而没有和 job 请求
核对，batch 又把输出 divisor 覆盖成 job 标签，形成错误的“18/18”摘要。

因此 `RC-formal01` **整批无效**：只能算额外 DIV1 开发数据，不能证明 DIV2/4，也不能将旧 summary
中的伪分组比值用于结论。831文件、636158467字节全部保留；jobs SHA-256
`a64c24eb1ffad179bb8ec6d4b484f600728d37f07bade896b7ca7a8a45f6a747`，旧 summary SHA-256
`85b34308aacda2fbd9fa3be843fb12cbcce5cd5ad80955a43cec43969f1b5c4b`，并由
`RC_INVALID_AUDIT.json` 明确标记不可接受。

修复已加入三层防线：runner 在 inherited setup 后恢复 job divisor；分析强制 requested=actual；batch
不再用 requested 标签覆盖 actual。按冻结的“一项一次、不自动补飞”规则，本轮不自行再跑18次。

## 4. 测试、失败与停止点

最终回归命令及退出码：`py_compile`=0；`test_remediation.py` 4/4=0；`make tests
TESTFILTER=ProperIsta` 3/3=0；`StaAxesApplication` 1/1=0；`StaProtection` 1/1=0；
`ControlDecimation` 1/1=0；`RateControl` 5/5=0；`make px4_sitl_default`=0。后两个过滤集合有1个
Proper内核用例重叠，因此共执行11个C++ test invocation、10个唯一测试，全部通过。

开发过程中保留：一次旧 StaProtection 断言未更新、一次
ControlDecimation 测试初始化笔误、一次缺 PYTHONPATH 导致 empy 导入失败、R-B 0-flight runner门禁失败，
以及 R-C 全批配置无效。前四项修复并回归；R-C 不重跑。

未做实机、DP1000、I06训练或I07正式留出；没有 push。解除阻塞需要用户明确授权新的 R-C v2 预算
（18次，原种子是否复用也需冻结决定）；通过后才能把 remediation 标记完成并重新启动 I06。
