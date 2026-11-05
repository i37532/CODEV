# RI06 最终结果（仅开发与独立验证）

- 54计划/54尝试/54起飞/54接受，54独立回放、36配对/468项风险检查通过，0飞行失败或补飞。
- 唯一选择：PID1.1倍、R-STA0.9倍、R-ISTA1.1倍；epsilon固定。详细规则与有限搜索局限见[报告](../../../../reports/RI06.md)。
- [package.json](package.json)：完整54行、来源/参数/指标、正式A80+B120共200项**全部unattempted**和完整资产指纹；不是飞行授权。
- [summary.json](summary.json)：A共同参数开发n2、B独立验证n3及n20精度示意，不能当正式结论。
- [ulog_index.json](ulog_index.json)：108份外部原始ULog路径/长度/SHA-256。
- [audit.json](audit.json)：重建核对、160项实际测试和证据。大日志和完整命令输出外置，不提交ULog。

第一次严格JSON导出失败完整保留在[final01](../final01/FAILURE_CN.md)。本目录export.py仅对12个精确估计器诊断路径的正无穷做显式可逆编码；其他非有限值仍拒绝，不改冻结分析器/判决或填0。serialization_checks.py有14项测试，audit.py可读原日志及冻结Git版本重算结果，均不会起飞。

正式源码候选为`16113b0ab3a0569755a11282dfc79cfed148f66b`、固件`b7548e2cc08208972e42501d1faf9e793a027224d30790264e9d16b316fcaaa1`。本结果提交仅结果/文档，不把它冒充已取得飞行资格的二进制。训练版本另见报告。RI07须单独启动并校验清单执行链；未push、未运行正式留出。
