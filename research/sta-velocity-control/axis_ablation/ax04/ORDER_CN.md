# AX04：冻结40个配对块的准确顺序

每行8轮，共320轮；每轮完整重启/预热/参数恢复。下列仅是清单，不代表已经执行。

| 轮次 | 任务 | IMU种子 | 配置先后 |
|---|---|---:|---|
| run001–run008 | H | 52020 | Z → XY → Y → XZ → X → YZ → PID → XYZ |
| run009–run016 | H | 52008 | PID → X → XYZ → Y → YZ → Z → XZ → XY |
| run017–run024 | H | 52019 | Z → XY → Y → XZ → X → YZ → PID → XYZ |
| run025–run032 | H | 52006 | Z → XY → Y → XZ → X → YZ → PID → XYZ |
| run033–run040 | H | 52011 | Y → Z → X → XY → PID → XZ → XYZ → YZ |
| run041–run048 | H | 52012 | PID → X → XYZ → Y → YZ → Z → XZ → XY |
| run049–run056 | H | 52016 | X → Y → PID → Z → XYZ → XY → YZ → XZ |
| run057–run064 | H | 52018 | XYZ → PID → YZ → X → XZ → Y → XY → Z |
| run065–run072 | H | 52010 | XZ → YZ → XY → XYZ → Z → PID → Y → X |
| run073–run080 | H | 52007 | PID → X → XYZ → Y → YZ → Z → XZ → XY |
| run081–run088 | H | 52001 | YZ → XYZ → XZ → PID → XY → X → Z → Y |
| run089–run096 | H | 52004 | XY → XZ → Z → YZ → Y → XYZ → X → PID |
| run097–run104 | H | 52003 | Y → Z → X → XY → PID → XZ → XYZ → YZ |
| run105–run112 | H | 52017 | Y → Z → X → XY → PID → XZ → XYZ → YZ |
| run113–run120 | H | 52009 | XZ → YZ → XY → XYZ → Z → PID → Y → X |
| run121–run128 | H | 52015 | YZ → XYZ → XZ → PID → XY → X → Z → Y |
| run129–run136 | H | 52013 | X → Y → PID → Z → XYZ → XY → YZ → XZ |
| run137–run144 | H | 52005 | X → Y → PID → Z → XYZ → XY → YZ → XZ |
| run145–run152 | H | 52002 | XYZ → PID → YZ → X → XZ → Y → XY → Z |
| run153–run160 | H | 52014 | XY → XZ → Z → YZ → Y → XYZ → X → PID |
| run161–run168 | V | 52016 | X → Y → PID → Z → XYZ → XY → YZ → XZ |
| run169–run176 | V | 52001 | XY → XZ → Z → YZ → Y → XYZ → X → PID |
| run177–run184 | V | 52019 | PID → X → XYZ → Y → YZ → Z → XZ → XY |
| run185–run192 | V | 52007 | Z → XY → Y → XZ → X → YZ → PID → XYZ |
| run193–run200 | V | 52002 | YZ → XYZ → XZ → PID → XY → X → Z → Y |
| run201–run208 | V | 52013 | XZ → YZ → XY → XYZ → Z → PID → Y → X |
| run209–run216 | V | 52010 | XZ → YZ → XY → XYZ → Z → PID → Y → X |
| run217–run224 | V | 52004 | PID → X → XYZ → Y → YZ → Z → XZ → XY |
| run225–run232 | V | 52009 | XYZ → PID → YZ → X → XZ → Y → XY → Z |
| run233–run240 | V | 52008 | Y → Z → X → XY → PID → XZ → XYZ → YZ |
| run241–run248 | V | 52011 | X → Y → PID → Z → XYZ → XY → YZ → XZ |
| run249–run256 | V | 52005 | YZ → XYZ → XZ → PID → XY → X → Z → Y |
| run257–run264 | V | 52014 | XYZ → PID → YZ → X → XZ → Y → XY → Z |
| run265–run272 | V | 52015 | Y → Z → X → XY → PID → XZ → XYZ → YZ |
| run273–run280 | V | 52017 | XZ → YZ → XY → XYZ → Z → PID → Y → X |
| run281–run288 | V | 52018 | YZ → XYZ → XZ → PID → XY → X → Z → Y |
| run289–run296 | V | 52012 | XY → XZ → Z → YZ → Y → XYZ → X → PID |
| run297–run304 | V | 52020 | Z → XY → Y → XZ → X → YZ → PID → XYZ |
| run305–run312 | V | 52003 | XY → XZ → Z → YZ → Y → XYZ → X → PID |
| run313–run320 | V | 52006 | XYZ → PID → YZ → X → XZ → Y → XY → Z |
