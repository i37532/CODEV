# V08 validation02：独立验证结果

飞行源码：ffe57be3542a8fb4c5e5148df9c6163b79c8d55a，protocol03b，40301–40303。
hover/figure8 × PID/XY ESTA × 3，共12/12接受、6/6配对；命令退出0，无补飞。
selected pid2/esta0保持training02结果；原位置P、Z速度PID、姿态/rate PID、DIV1不变。
旧validation01的5接受/1失败不拼接、不改判。

`summary.json`含准确清单、指标及24份ULog路径/指纹；`original_artifacts.sha256`核对694原始文件，
索引SHA 28d5bf08a1b9d974a3185fd82a31b2e9d6cf1b02c881ce4d0595b2157d43ccde。
原数据：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08/validation02。
ledger SHA 75c393f6bc546c711d56a8629f0dc578c9852239366bbb745bc9448114816e49。
`replay.json`：12轮隔离全链回放退出0，除已审计的counts字典顺序外指标完全一致。
`verification.json`：干净飞行源码231 C++/554 Python、1815资产及构建通过。
固件7449793e7424b56aad016bd4d0c9d585337c04808051ef6931e063fc642e085b。
原EEPROM恢复为06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，无残留仿真。

`development_summary.json`仅开发描述统计：ESTA悬停/8字XY误差约低12%/25%，纠偏TV约为PID两倍。
每任务仅3个配对种子，不能当正式检验。宿主耗时的原键名虽含ns，分析值已转换为μs；均为各轮分位数的均值，非合并样本分位数、板级CPU或WCET。
`snapshot.sha256`覆盖生成时的小证据副本；本说明和后加的development_summary不冒充原始飞行工件。
安全先导和正式设计包未完成，V08未验收。未push，正式试验0。
