# 修订分析器和17轮续跑入口交付

实现提交：`9eabf3993f7e7b4801b9a81dffc7b24872aa431b`。
研究分支；本轮没有启动Gazebo或新飞行，没有改控制器、消息队列、模型和参数。

## 实现与限制

`i05/analyze.py`默认strict行为保留。显式amended-v1要求独立新输出目录，复制最小分析输入并
记录原文件指纹、原接受结果、分析器提交与工作区状态。原ULog通过绝对路径只读访问且重新验SHA。
共同的起降、模式、参数、输出、公式、时序、状态隔离及性能指标检查仍完整执行。

`i05/logging_acceptance.py`对有效飞行窗口所有匹配记录核对力矩和推力（包括保持回调），拒绝
非有限值、空交集、逆序/重复、无法匹配状态的执行器时间戳以及窗口/正负激励证据不足；分别输出
各窗口和激励段更新/保持缺样数量、比例、最大间隔。缺样只披露，不插值补样或宣称完整发布验证。

`i05_remediation/continue_rc.py`默认只检查17轮清单；`--assess-first NEW_DIRECTORY`只离线重分析；
`--execute --first-assessment DIRECTORY`才实际飞行。续跑固定使用原索引1–17、种子7001–7003，
每DIV完成6项（含原第1轮修订结果）后裁决，再升级。失败立即停止，目录拒绝复用，不自动重试。
执行前要求干净提交、原预算/输入指纹一致、固件/模型非研究路径无差异、子模块一致、冻结插件和
来源指纹匹配；构建后冻结新固件SHA，各轮检查启动器实际源码及二进制一致。
原轮与续跑二进制不同的版本元数据分别记录，不伪装成同一固件。

清单中的execution_source_head占位由执行时binding.json明确绑定。原轮重分析后只允许追加reports
目录的结果记录；代码或协议改动必须重新离线分析。宿主编译器版本将记录在binding中，生产源码、
工具链或环境发生实际变化时仍需审查，不能把软件指纹核验等同宿主调度可重复性保证。

## 验证结果

- 新增8个测试通过：缺样披露、保持期推力不一致、空交集/逆序/重复/陌生时间戳/NaN、窗口及正负
  激励证据不足、17轮顺序与三个门控、首个失败立即停止、DIV1门控失败不启动DIV2、拒绝重飞索引0。
- 既有4个采集审计测试及5个remediation测试通过。共17个唯一Python测试；新增8个提交后复跑通过。
- py_compile及diff检查退出0。没有C++变更，未宣称重新运行C++或SITL。
- 清单入口在干净实现提交上退出0，打印17项；未加--execute，未调用启动器。
- 完整首轮amended分析退出0，strict副本分析按预期退出1，错误仍为Missing hover actuator update。

## 首轮独立重分析

目录：`/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RC-first-amended01`。
`i05_analysis.json` SHA-256：`f1e6e0885e57d448fd7f58e34cce79a40f263ade539d7b39183a7e98771a0084`。
original_acceptance=false，revised_acceptance=true，分析时工作区干净。
状态悬停15063条，0缺样、250Hz；执行器悬停996条时间戳缺口如实保留，匹配输出一致；
最大倾角1.53187°、高度误差0.126558m、悬停饱和比例0、ULog写入dropout=0。

strict验证目录：同一I05R下`RC-first-strict-check01`；分析SHA-256
`0a0e02cee50e38300da33974c74f9e97d7a53a461fb7b3666613e3b6f443afbf`。
原formal03分析SHA仍为`488a8f9b4cd11815970a4b6822f9d549c9820059fb258baaec02a8ed79dcb43c`，未改写。

## 使用

在仓库根目录设置项目PYTHONPATH/PATH，按remediation/README_CN.md使用。
原轮修订分析已可供续跑入口核验；以下命令会实际启动预算，应在执行17轮时调用：

```bash
python3 research/sta-rate-control/ista_redesign/i05_remediation/continue_rc.py --execute \
  --first-assessment '/home/yr/Desktop/codev doc/experiments/ISTA-REDESIGN-20260918/I05R/RC-first-amended01'
```

本轮交付完成；17轮尚未运行，I05尚未最终验收，I06仍不可据此宣称前置通过。未push。
