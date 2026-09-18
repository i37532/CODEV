# I00 算法总结勘误：h² 的适用条件

日期：2026-09-18。对应 `SUPER_TWISTING_FAMILY_CN.md` §5.6 与 §6，不改写历史实验或原算法。

原 §5.6 关于“有扰动时 h² 量级精度”的概括遗漏了关键条件：本地原论文 Definition 1 定义的离散滑动面要求 **virtual_s=0 且 nu=0**，Lemma 4 以此前持续属于该集合为前提。原文明确未证明受扰时该集合的不变性和可达性。

对于原 MATLAB/当前 MODE=2 使用的控制律，理想固定周期对象 `s_next=s+h*(a+d)` 在恒定非零扰动下存在平衡点：

`s=h*d, nu=-d, a=-d, virtual_s=0`。

它不满足 nu=0，因此不能套用前述条件得到一般 O(h²) 精度。I00 已用未修改的生产 C++ 内核、独立双精度参考及独立对象复现此关系；不代表已证明所有真实飞行都会处于该平衡点。

原 §6 中“大步长通常优于 ESTA”的历史概括也不应扩展为 RMSE、起降成功率或所有指标保证。更小的数字抖振和更小的真实偏差是不同问题。

追溯资料：

- [完整公式、量纲与代码审计](/home/yr/Desktop/Codev-autopilot/research/sta-rate-control/ista_redesign/i00/THEORY_AUDIT_CN.md)
- [本次验收报告](/home/yr/Desktop/Codev-autopilot/research/sta-rate-control/reports/I00.md)
- [勘误前算法总结全文](/home/yr/Desktop/Codev-autopilot/research/sta-rate-control/ista_redesign/i00/sources/SUPER_TWISTING_FAMILY_CN.pre_I00.md)

原论文采用本地 `BBSTA.pdf`，HAL hal-02336599v1；后续 Proper-ISTA 数学规格固定 [arXiv:2406.16094v1 PDF](https://arxiv.org/pdf/2406.16094v1)。文献原件指纹及页码见完整审计。本次没有实现新算法，未执行 MATLAB，未修改保护，也没有新飞行。
