# V07 第五批：1接受，真实ULog dropout停批

源码914c2213d895f842c723c64d3fa14fc374833950；2尝试/1接受/1失败/16取消/0配对，不是V07通过。第2轮起飞期在线记录过旧，完整ULog有0和912ms dropout，数据不可修复或补造；没有进入降落pending路径。

summary保存1轮独立完整分析，recording_audit保留失败dropout详情，archive/raw_artifacts列4ULog及332外部工件指纹。工具快照按原外部V07-LIVEPOLL目录组织，勿原地覆盖重跑。下一批实时tmpfs隔离方案需另冻与验证，旧失败不改判。详见../../reports/V07.md。
