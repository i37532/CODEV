# R03 revision09结果与D预解锁停点

实际源码eb25fecbdba9a499132a16ce16f6b847e4a218d3，固件SHA-256 4b62cde850d5612cccb7392acfd7b2040b98e18c61efb2eaa98d3162154f98cc，33递归子模块不变。原飞前报告R03_REVISION09.md保持原样，本文件补充实际结果。

| 门 | 计划 | 尝试/起飞/接受 | 独立回放 | 配对检查 | 结论 |
|---|---:|---|---|---|---|
| A/X | 9 | 9/9/9 | 9/9完全一致 | 6/6 | 通过 |
| B/Z | 9 | 9/9/9 | 9/9完全一致 | 6/6 | 通过 |
| C/XY | 9 | 9/9/9 | 9/9完全一致 | 6/6 | 通过 |
| D/XYZ | 9 | 1/0/0 | 未进入接受回放 | 0 | 首轮预解锁失败，8未执行 |

四门均先在干净源码分别执行qualification01：各70命令exit0、541不同C++/1443 Python、32768固定逐样本对/256同sample重算、6旧ULog诊断CLI及SITL/Gazebo构建通过。D资格不等于D飞行验收。实际revision09为28尝试、27起飞、27接受、1失败；整个R03累计82尝试、80起飞指令、73接受、7失败、2诊断。没有完成原同HEAD36要求，R03仍未验收。

## 原始证据

外部根：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision09/。各门batch01、replay01、qualification01完整保留。所有批次参数精确恢复、remaining_simulators=[]。

- A gate_pass SHA 03654f4015a6b2110353749e654eef3108eae2e30970b2dbdff6b86feb9686ad；replay summary 312519c53f05d154e259a8c9e559f14cb326d190da686959bdb2ed003ce0045d。
- B gate_pass 19be1806782b4af196cff4282c80d9e2167d5a5e5c38f95865353a04a957fdf2；replay db4c325cdf2f9ccd0190fe7bbd64d3d74dbae457216d5fc5ce357ffa3e452a41。
- C gate_pass 58cebb1f1f2fec1a2ecb76d299954ec281d068e646dd980f72e6386c0c9e29df；replay ad53c51917dcda6860c547da15c7800305966309ac8fea7dd279ddf15347388d。
- D ledger 6ffaf5316cab0be860e198612ed098ca5e4d8b4305e88c0aae82705fb518fba4；journal ff470dac7ae78ce47f9d888f9978a606d99e9ff6b511a1328188febce5822a07。
- D/run028/log001.ulg：119870字节，7f49dd73f5eb091306872d90946e43176a5c867088a0a0a33eb1ebf3cbace885；startup 08_33_06.ulg：27424650字节，feb734dec7ce75d28a01a690044f0e24b022255da995f1694aa968a23947ed0e。

## 根因与离线复现

D唯一event为ready（38516000us），没有takeoff_command。原错误ValueError('Missing attitude boundary predecessor')。起飞前重验累计原始证据耗时使PX4开机时间已超过30秒；logger随后重启，旧ready却仍看自开机时间。warmup只完成一次读取，snapshot_end=101918字节；紧接prearm读取0新增字节，参考时刻之前没有必需姿态边界。完整短日志只有约20ms姿态/本地位置范围。

r03_warmup10/test_failed_prefix.py按原归档SHA和实际在线截断字节解码，调用原PositionLogView/reference_row，精确复现同一异常，exit0；新逻辑在该时间点保持未就绪，原边界检查仍拒绝。不是修改姿态时间规则、去重或降低500ms标准。旧失败不改判。

## 下一有限修订及限制

revision10仅增加首次完整新owned日志读取后的30秒仿真相对预热。新D九轮、新种子71731–71733、总91=82+9；旧D八项不续。ABC保留原版本，D的新runner/源码/固件版本戳、地面预热差异明确披露；不宣称同二进制36次，不跨任务合并统计。生产控制、参数、模型不改，首败仍停批。详见AUTHORIZATION_R03_REVISION10_CN.md及其协议。

A run005有描述性4ms time_slip，其他A与全部B/C最大为0；无原超限age事件。UP08已知非主EKF诊断8ms及初始28ms原因未完全证明的限制仍保留。不以这些描述量新增事后阈值。未执行MATLAB、板级CPU/实机、R04/R05。
