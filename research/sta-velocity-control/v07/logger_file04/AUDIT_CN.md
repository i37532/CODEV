# V07 解锁前日志文件重名：离线审计与第四批协议

用户持续授权修复日志链到V07通过，无需逐次起飞申请。第三批在16/18次停止：15接受、1解锁前失败、余2取消；不改判，不把未起飞失败当作成功飞行。

## 真实原因

series03/run16的console.log第73/187行均是`./log/2026-09-29/03_52_10.ulg`。旧logger关闭174554字节后，同路径第二次打开并最终写20986360字节。result仅ready事件、最后状态disarmed/landed，严格新路径归属检查失败。存活主ULog SHAd7f19644f913fb270233a2d0ee06ef6844ac819c4e616b27748abc1e10d2c0ee；旧启动前缀已被旧写入行为覆盖，不能恢复或假称两份都保留。

生产链：logger `instantiate`默认log_name_timestamp=false，`-t`将其置true；`get_log_file_name`的日期分支采用`%H_%M_%S`，不检查同路径已存在。util::get_log_time优先合法GPS UTC，其次REALTIME，不能以宿主sleep保证GPS命名秒一定改变。LogFileBuffer::start_log是O_CREAT|O_WRONLY，没有O_EXCL，从头覆盖而非追加；若新日志短于旧日志还存在旧尾残留风险。本轮新日志更长。这里只确定两次同名，不虚构本次精确GPS/RTC切换调度。

## 最小修复

只在新protocol04运行器去掉重启实验logger的`-t`。已有生产session分支原样使用mkdir的新目录排他创建及已有文件检查：每次新logger得到sessNNN/log001.ulg，命名不再依赖UTC。保留stop/原1.1s屏障、-b256/-r1000/-f、profile1171及唯一文件前置检查。不是增加sleep或把被覆写旧路径当新日志。

新增owned_log检查恰好一个新文件、session格式、普通文件且无symlink逃逸；原直播inode/截断/128MiB/ULog完整性和位置队列全部保留。没有生产C++改动，没有改控制律、dt、参数、world、模型、种子作用域或数值门槛。未修复整个上游-t行为，也不声称其他应用的时间命名已安全。

## 离线验证与新批次

- 独立真实C++ probe链接实际modules__logger，用-fno-access-control仅供测试，不运行logger线程：无-t解析、重启新session且旧字节保留、同session递增文件、固定GPS秒复现旧-t重名，共4项。临时目录由mkdtemp唯一创建，保留以便检查，不清理用户目录。
- 7项Python：精确重启argv、stop失败不继续、唯一文件与旧字节、没有新文件/旧路径重写、多个writer、日期路径/symlink拒绝、真实运行器接线。继承16项队列和全部回归，不减少旧测试。
- source/协议提交前及干净提交后完整回归；预计226 C++/471 Python，以实际evidence为准。profile256注册与ULog格式、默认PID2×2048、SITL/Gazebo构建继续核验。
- 新protocol04全18次，不拼接旧成功：32001–32003 DIV1，32004–32006 DIV2，32007–32009 DIV4，各PID→XY ESTA，逐门每3配对通过才推进。旧所有失败/取消清单保留。相同90–92s观察/64s固定yaw低速8字、2.5m、原软接触、XY ESTA+Z PID、全rate PID；原参数/性能/安全/日志门槛不动。
- 新根`/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V07-LOGFILES/series04`；先冻结种子和源码，再干净验证和执行。第一失败停批，持续授权只允许查明后修复、另冻有限批次，不盲目重试、补飞或放宽门槛。
- 结果独立回放、日志路径/指纹/命名覆盖审计、参数恢复后写V07报告及进度完整SHA；不push/ISTA/实机/V08。
