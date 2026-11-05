# R01 冻结逐样本参考

来源为完整提交 `9d1c74fce9fa386e94e790514aeb8f2c718abc47` 的 `src/modules/mc_pos_control/PositionControl/`。
五份源码只依次机械替换 `StaVelocityProtection`、`VelocityControlSelector`、`PositionControl` 为相应 `R01` 前缀（含类型、头文件、注释中的同名串），没有修订数学或状态处理。
`r02/verification/verify.py` 每次通过 `git show` 重新验证完整内容一致并记录 SHA-256。

参考库仅在 `BUILD_TESTING` 时构建；共享本阶段未改的旧 `StaVelocityControl` 和 `ControlMath`，不宣称完全独立重写的数学证明。
`RegularizedVelocityRegressionTest` 对 MODE0/AXES0 与 MODE1/AXES1…7 各执行两组2048步，固定10ms及交替8/12ms；合计32768对主样本，另256对同sample二次调用。
有限float按比特比较，NaN比较无效语义而不限定payload；对照输出、积分、nu、保护状态、配置时序、限幅与HTE，保留PID旧dt语义。

参考不包含新MODE3，也不证明新模式飞行稳定；新版保护/交接的独立负例和模块uORB测试另计。
