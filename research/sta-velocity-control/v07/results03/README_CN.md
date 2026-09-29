# V07 第三批结果：15接受，文件重名停批

源码ddec13d525b0f41bbf77cfad3a3487445d198007；16尝试、15接受、1解锁前失败、2取消。DIV1/2通过，DIV4未完成。没有把脚本退出0或位置记录完整等同V07通过。

summary.json为15轮独立回放及描述性指标；recording_audit.json记录16次位置副本完整性和原通道2条漏记；filename_probe.json是额外4项实际C++命名诊断。archive.json和raw_artifacts.sha256给出外部原始路径与指纹。tools_snapshot脚本按原外部根设计，postprocess/audit不可在仓库快照目录直接重跑；复核应建立独立输出，不覆盖原结果。

第16轮只有一次logger重启后存活的主ULog：旧秒级命名复用了启动路径，启动前缀已被覆盖，无法恢复。没有解锁/起飞；控制台、命令、主ULog、失败判定均保留。大日志在外部V07-LOGCHAIN，不入库。详见../../reports/V07.md。
