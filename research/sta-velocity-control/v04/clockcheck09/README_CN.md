# clockcheck09：姿态双时间离线验收修订

这里只是离线实现，**不是可执行飞行协议**：flight_authorized=false、execution_ready=false、预算0，无新种子。旧批次与失败不改判，不能续跑旧剩余五轮。

规则见[contract.json](contract.json)，结论见[修订报告](../../reports/V04_CLOCK09_REPAIR.md)。新政策必须显式传入`AttitudeClockPolicy()`；现有飞行入口默认仍走旧规则。只有公共`vehicle_attitude:0`允许发布同刻，不放宽其他连续话题。

```bash
cd /home/yr/Desktop/Codev-autopilot
export PATH="$PWD/.px4-python/bin:$PATH"
export PYTHONPATH="$PWD/research/sta-velocity-control/scripts:$PWD/.px4-python:/home/yr/Desktop/codev doc/experiments/M00-20260912/python${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest test_v04_attitude_clock09 test_v04_clock09_integration -v
# --output必须是全新且不与原始数据重叠的目录，不覆盖旧结果。
python3 research/sta-velocity-control/scripts/replay_v04_clock09.py --output '/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260926/V04/clockcheck09_replay_new'
```

回放程序退出0仅表示七批回放及输入完整性检查完成，**不是七批飞行通过**。查看`evidence.json`各分项的check_passed/error；顶层accepted始终false。隔离目录里的baseline/core组件accepted只属于对应组件，不能当整轮验收。只有series05有完整起降，可用于组件等价对照；其历史整轮失败仍保留。

发布时间/采样时间分别报告频率，yaw沿用逐记录等权口径，速度主指标仍用原sample时间权重。姿态到rate的实际消费无法由同刻发布推断；新版唯一关联接口拒绝歧义，描述接口保留所有候选，不猜测、不去重。
