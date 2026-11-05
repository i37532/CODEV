# RI01 — 独立补偿 R-ISTA 速度核

[阶段报告](../../reports/RI01.md) · [数值与事务约定](NUMERICS_CN.md) · [对象规格](model/SPEC_CN.md) · [对象结果](model/RESULTS_CN.md)

新库仅用于测试，默认PID和MODE4拒绝逻辑未变；无飞行入口、无参数加载、无新种子。旧ESTA只做兼容回归，不加入新实验比较矩阵。

## 离线验证入口

~~~bash
cd /home/yr/Desktop/Codev-autopilot
python3 -B research/sta-velocity-control/regularized_ista/ri01/verify.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI01/<新的唯一目录>'
~~~

入口要求RI01开发基线HEAD=e8e38752499c12b9c39bb7dc95da58f27ff029d4及明确生产改动清单，避免误在另一阶段给出资格。阶段提交后如需原样复现，应在独立检出中准备该基线加RI01补丁，或另冻新的验证入口；不要回退/清理当前工作区。上述占位目录需替换，原有证据目录拒绝覆盖。

脚本内部记录全部argv/exit/log SHA、移除继承的GTEST过滤/分片、生成并运行38个相关测试目标，按XML实际完成用例去重；不把make/CTest重复执行计作更多独立测试。保存EEPROM和原固件指纹及副本后，仅构建SITL固件，不调用Gazebo启动命令。随后检查新核未进入实际固件和生产编译数据库，运行最终独立对象/fixture检查。

只重跑对象可用：

~~~bash
python3 -B research/sta-velocity-control/regularized_ista/ri01/model/check.py \
  --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-RISTA-20261024/RI01/<新的模型目录>'
~~~

无需MATLAB可执行文件；这里对已有MATLAB CSV核对，不能称重跑MATLAB。原包和旧日志只读。

## 证据与限制

最终主验证目录、真实数量和失败修订见阶段报告及results中的小证据。原始编译日志、gtest XML、对象逐步CSV、共享库、固件副本留在外部并索引SHA。

对对象区分：完整时长、正常float量域耗尽提前停止、不可行限幅反例。后两者不称完整跟踪通过；受保护输出不称严格隐式解。没有新飞行、实际推力比较、HTE/起降新适配、正式调参或实机验证。

只允许进入待授权的RI02离线接线；当前不能直接切换MODE4飞行。原R04/R05继续暂停。
