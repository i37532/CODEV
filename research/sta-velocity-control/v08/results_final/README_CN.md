# V08最终离线验收

正式协议源码392d61ca9876dd5e3bf27ad4b746e4f0f6c8c62b，在干净提交实际231 C++/621 Python、2495资产及SITL/Gazebo构建通过，退出0。
verification.json记录精确命令和用例数；verification_artifacts.sha256指向外部完整测试日志，未把mock的200次调用写成飞行。
closure.json的只读复核全部通过：4359原始工件条目、148ULog、2495资产、33子模块、参数恢复、生产目录零差异、正式0次。
check_closure.py可用--output全新路径复查，不启动模拟器。当前固件是正式源码构建；以后重建其他HEAD须重新核验，不覆盖此证据。
原始根/home/yr/Desktop/codev doc/experiments/VELOCITY-STA-20260929/V08；正式未来目录VELOCITY-STA-V09-FORMAL01尚未创建。
详细结果/范围/偏离和下一阶段准确200预算见reports/V08.md及formal/README_CN.md。
