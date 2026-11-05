# V08 首批训练停止记录（未验收）

source c2e6c0be8490c1ebe2250859f5cdc10252941f63；13尝试、12接受、1失败、11未执行。
12接受均hover；第一次figure8的esta2因在线监视器跨读取时间比较中止。没有补飞/选参/验证/先导/正式试验。
状态needs_revision，不能将离线审计完成称V08通过。

- summary.json：真实清单、每轮指标/状态、26份原始ULog路径与SHA、测试命令退出码。
- ledger.json、training01_command.json：原批次台账/退出1。
- verification_committed01.json：干净飞行源码231 C++/522 Python、构建及1463资产通过。
- replay01.json：12轮独立重放退出0，metrics逐字相同。
- failure_audit01.json：第13轮离线时钟/序号/消费关联与模式证据；不改判。
- runNN：原result/job、参数、模型指纹及已接受轮metrics；不是重新生成的成功记录。
- original_artifacts.sha256：外部训练目录729个原始工件完整索引；不包含大型ULog本体。
- snapshot.sha256：生成时的小证据副本指纹（不包含后补的本README）。

外部训练目录：`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/training01`。
参数备份/恢复保留。没有删除失败/原始字节；旧V07日志不改。
不从这12个hover结果选择参数或作正式优胜结论；见reports/V08.md后续准入项。
