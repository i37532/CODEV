# R03 revision10：日志相对预热及新XYZ门

## 飞前状态与范围

入口eb25fecbdba9a499132a16ce16f6b847e4a218d3，research/sta-velocity-regularized；33递归子模块未改变。之前提交的生产实现保持，包括UP08修复；本次只新增独立运行器/分析器/回放/资格/冻结、预热组件及测试、版本化计划和报告。旧目录、参数、世界、模型、源包和失败原判不修改。无实机、ISTA、R04/R05。

revision09结果及真实预解锁根因见R03_REVISION09_STOP.md。旧ABC各9接受/9回放/6配对保持原版本；D失败1次、零起飞，8未执行。历史82尝试/80起飞/73接受/7失败/2诊断。用户持续授权有限必要修订，新D9、累计上限91；种子71731–71733扫描65937份JSON，无冲突，四份精确登记SHA豁免不覆盖实验目录。新清单尚未飞行，不将旧失败或诊断算新接受。

新预热只在第一次完整新owned日志读取时定锚，等待至少30秒仿真sample所读发布时间差；原180秒宿主超时、500ms新鲜度、完整边界/reset和安全条件不变。收据由独立实现交叉核对samples、原增量解码计数及raw prefix证明。不得把开机时间当日志历史。原reference_row异常不捕获重试，缺样/时钟/失败仍拒绝。

ABC与新D的runner提交、固件版本戳、地面预热不同，明确版本化取代未达成的同HEAD36条款；生产控制与127参数/资产相同，不混池、不声称同二进制36次。新D九轮同一新干净源码/固件；每个任务各算法n=3开发证据，非正式总体结论。

## 离线检查与复核

预提交verification01实际进程exit0：78命令全0，541不同C++、1653 Python；32768固定逐样本对及256同sample重算，SITL/Gazebo构建通过。新revision10分项187项（分析57、数值16、协议17、回放44、运行器53），warmup10分项23项（独立证据9、真实失败前缀1、状态机13）。旧revision09 185项也完整重跑，未把旧计数当本次执行。全部逐文件独立进程避免历史通用模块名碰撞。

三份旧revision06 ULog各两种导入顺序，六次CLI回放exit0，旧run030仍失败、输入指纹未变。实际revision09 D/run028的101918字节在线截断回放精确复现Missing attitude boundary predecessor；旧ULog指纹不变，新逻辑不提前就绪。不存在把离线合成成功当飞行成功。

统一证据目录：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision10/D/verification01。evidence.json SHA-256 f9468a57f6cc672293e18c59691601c2e35e7f3d5389ff5faa71f87fee03a76d。逐条命令、退出码、GTest XML、Python计数、环境与输入SHA在该目录。此收据clean=false，不授予飞行资格。

适配过程中旧预算/旧fixture假设和新warmup字段缺失等测试先失败，修订夹具并修复None类型拒绝后通过；首次无PYTHONPATH的dry-run因numpy不可见exit1，未触及飞行。不是隐瞒失败或调低科学门槛。预提交验证后仅更正runner顶部文档字符串（准确说明新增预热）并重新绑定其冻结SHA；实际可执行语义不变，最终干净资格仍须全量重跑。

冻结837项仓库/派生资产、79外部资产、33子模块；冻结旧revision09四份资产清单及全部旧执行依赖。飞前差异审查：生产路径无变动，旧科学函数/预解锁完整检查AST一致；flight body仅新增warmup_ready调用和与原ready的AND，两处逆变换精确回到原函数。风险/参数/目标来源不变。原EEPROM SHA保持06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc，磁盘约53GiB空余。

## 复现入口

在仓库根目录，先配置项目现有依赖：

```bash
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/.px4-python:$PWD/research/sta-velocity-control/scripts:/home/yr/Desktop/codev doc/experiments/M00-20260912/python"
python3 -B research/sta-velocity-control/regularized_sta/r03_revision10/runner.py --gate D
```

最后一条默认只展示冻结清单。资格命令为verify.py --gate D --qualify --output 外部R03_revision10/D/qualification01；必须在新干净提交执行。实际飞行入口额外使用--execute --source-head 完整新提交SHA --qualification 准确evidence.json。完成后使用同目录replay.py的回放及finalize入口，不能用旧资格替代或直接重跑已有batch01。

本报告飞前版本未执行新九轮、MATLAB或实机。首个必需失败停批并保留原始数据；结果和SHA在真实完成后单独提交/更新，不能预填通过。
