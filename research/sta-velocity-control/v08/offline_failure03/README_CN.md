# 第三次V08审计：质量场景在起飞前被严格模型检查拒绝

2026-10-05恢复任务后核实：pilots01共13尝试，前12（heading/force各6）通过，第13质量PID预检失败、0起飞，余5未执行。
源码ce0704bcdfefd8b4501c2c06ed9556fe5b542469；实际运行日期2026-09-29，恢复工作日期不得冒充飞行日期。
旧failed不改判。EEPROM精确恢复，无残留模拟器。12接受均独立全链回放通过，值一致（counts键顺序例外）。

## 证据与覆盖缺口

原质量SDF rotor_0..3的Iyy=.00030041440000000002，实际加载=.00030041399999999999；Izz同样少4e-10。
质量及其他惯量大致正确，触发原1e-12模型检查。没有takeoff/armed试飞事件，不能据此评价PID稳定性。
早期ground_model_probe把model直接嵌入world，保留完整精度；真实项目Tools/sitl_run.sh经gz model --spawn-file走factory插入路径，未被该夹具覆盖。

新增无PX4/零重力fixture复现项目插入方式：

- transport_probe01：名义CLI通过、质量CLI复现误差；尝试sdf_filename绝对路径不被Gazebo model URI接受，退出1、0飞行，证据保留。
- transport_probe02：名义CLI/raw均通过；质量CLI及原文Factory.sdf都同样舍入。因先前假设raw保精度不成立，探针退出1，0飞行。不是只修CLI即可解决。
- transport_probe03：显式Q6惯量派生模型，名义/质量×CLI/raw四夹具严格比对均通过、退出0，0PX4/0飞行；7link质量/惯量/重心完整。结果副本revised_transport_evidence.json。

因此采取**可追溯物理模型协议修订**而非放宽验收：质量仍×1.10；惯量定义为Q6(1.10 I)，六位十进制有效数字。
转子最大相对改变量约1.3315ppm，几何/质心、电机和气动不改；声明这不再是数学上的严格全张量同倍率。
实际模型比对仍1e-12，控制律/dt/参数/原安全性能门槛不改；旧model白名单/分析器不动。
protocol05只重冻质量门40401–40403、6次新尝试。保留已合格heading/force两门，不将不同源码合称同批18轮。

原始根：/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08。
原失败证据：pilots01/run13；脚本各失败版本保存在transport_probe01/02的probe_transport_source.py。
当前probe_transport.py可用--revised-scenario重现实验；仅地面物理夹具，绝不是起降验收。
