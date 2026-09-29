# V07 第六批：隔离宿主磁盘写入，严格日志门槛不变

2026-09-29。起点 8d22162045d5e5789edd88554df3ceff823ff357，研究分支不变。

## 证据与边界

第五批仅2次：PID完整接受，ESTA起飞期间因真实ULog丢失停止，剩16取消，不拼旧批。
失败主日志SHA 4f489f4c957d1cee95501f6e8bdd1c94898c93e8251a19f4e76075deae279dfb。
ULog dropout duration为0和912ms，记录停在36.196/36.204s而CLI位置已37.104s。
约701KiB/s和256KiB缓存下磁盘写入停顿是合理线索，但没有syscall跟踪，不能断言fsync已被证明是根因。
现场磁盘约67GiB可用、tmpfs约7.6GiB可用；dmesg无权限。没有杀其他应用或删除旧数据。

## 修订

仅Linux SITL明确设置PX4_SITL_LOG_DIR才重定向完整日志；只接受本人拥有、0700私有、真实tmpfs、无符号链接的/dev/shm/px4-v07-*目录。
默认路径、任务日志、硬件构建保持原行为。实际logger缓存、fsync代码、topic/profile/rate不变。
每轮新目录，飞行期间不复制磁盘；停机后独占创建归档，fsync文件和目录，比较源前后及副本SHA，保留RAM源。
归档失败使该轮失败，不默默接受。RAM在断电/重启前未归档时不持久，不称黑匣子保证。
已有队列副本/seq、256槽ID、唯一session、pending最多8次即时检查与原双500ms期限保持。
不修改控制律、dt、模型、参数、数值安全/性能、缺样/dropout或时间检查，不改第五批失败。

## 离线与新预算

5个真实C++测试包括原路径、环境路由/拒绝、权限/链接、实际writer线程写入排空；不启动仿真。
12个Python测试涵盖容量预检、所有者/文件系统/符号链接、归档一致性/不覆盖/fsync失败/源变动、运行器接线及飞行代码精确差异。
完整旧回归、SITL/Gazebo构建、参数指纹与冻结资产检查通过后才提交并在干净源码复核。
新protocol06：34001–34009，DIV1→2→4，每档3对PID/XY ESTA+Z PID，共18次；全rate PID。
任务、门槛、顺序、随机性限制、配置见execution.json。首失败停批，不续旧16轮，不补飞、不调参。
用户“修复日志记录链，后面不用我授权，一直到v07通过”为持续授权；无push/V08/ISTA/实机。
新外部根：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V07-RAMLOG。

## 历史保留

protocol01–05及results01–05全部保留，旧成功不能凑当前验收。
开发首次测试调用本身12测试通过；后续只读寻找不存在README/PROTOCOL文件退出2，不是飞行/验证失败。
第一次完整离线回归的writer夹具过早stop，可能在线程进入_should_run循环前丢一次性notify，5项中1项失败。保留verification_working06；修订夹具按生产调用方式持续notify并确认写出后才stop，未修改writer生产逻辑或放宽验收。
所有新验证实际数量、退出码、协议/结果SHA在最终reports/V07.md和进度表记录。
