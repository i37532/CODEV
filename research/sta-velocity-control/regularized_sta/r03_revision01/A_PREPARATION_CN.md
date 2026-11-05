# R03 revision01 A 门飞前准备

2026-10-16。此检查点只表示离线验证通过，**新飞行0、阶段尚未通过**。原失败1次、接受0保持。

修订入口为 `561d70c6ad368357542a9864a675030634391290`，33递归子模块干净无偏移；本次没有生产控制、参数或模型改动。只新增一次性授权、计划快照及新版研究工具。用户明确同意总预算37=旧无效1+新36，R04/R05仍54/200。

## 已实际执行

```bash
python3 research/sta-velocity-control/regularized_sta/r03_revision01/protocol.py --prepare
python3 research/sta-velocity-control/regularized_sta/r03_revision01/verify.py --gate A \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-REGULARIZED-20261016/R03_revision01/A/verification01'
```

使用README中的既有PYTHONPATH/PATH，不安装全局依赖。两命令退出0；全历史查重56566份JSON，12新种子无冲突。A使用71041–71043，后续B/C/D使用71051–71053/71061–71063/71071–71073，原未执行种子注册保留但本修订不用。

统一验证41条顶层命令全0，475不同C++、1021不同Python通过；32768对旧PID/ESTA主样本和256对同sample重算一致。635项输入指纹保持，EEPROM未变。SITL/Gazebo仅构建，无新飞行。证据JSON SHA-256：`2e4da7a49495b3c6a9698f3f6f37c30290302144d87237cd0b74ca10a2724dff`。

新Python测试146项=协议39+运行器36+分析器28+独立回放32+交叉审查11；原850项及repair01的25项也在此次统一链实跑，共1021。先前各组件重复执行不累加成新用例。两种真实导入顺序完整分析同一旧ULog，数值和频谱一致，诊断成功但accepted/flight_accepted仍false，不能当作两个新飞行样本。

## 修复与审查

新分析器显式绑定固定AX02三维height/task，保留旧完整数值与时钟/reset/降落/健康/尾部检查；新qualification/job/archive严格与旧失败分离。运行器保留原飞行主体、唯一目标源、BSON精确恢复和归档处理；新旧版本共享进程锁，首败停批。

只读审查发现资格payload原使用Python等号，`1/True`、`9/9.0`可能别名。修订为严格JSON类型比较并实际负例验证拒绝；不是飞行事故。freeze/verify也改为按本版绝对路径加载，污染generic模块名负例通过。旧r01/r02/r03入口Git快照不可变检查有效；完整127项参数、每门目标和数值门槛与旧版一致，旧失败不会因修复改判。

本阶段新统一验证无失败。另一次只读`ls test_revision_audit.py`在代理尚未写好时退出2，后文件完成并实际11测试通过；这不是控制或飞行失败。旧R03与repair01所有历史失败另见原报告，不覆盖。

## 仍需完成

资产冻结、明确文件提交后，必须在干净HEAD重新统一资格并重建当前固件；本次工作区验证的二进制不能冒充之后提交的资格。随后仅A九轮，无需再次询问。A九轮及六配对风险检查、九轮独立回放全部通过才开放Z；R03四门未全过不push阶段或进入R04。

未执行MATLAB、板级CPU、硬件、ISTA、调参、分频或额外先导。性能不预设新算法胜出，不能放宽门槛换通过。
