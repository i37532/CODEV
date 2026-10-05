# V08 pilots01：两门通过，质量预检停止

源码ce0704bcdfefd8b4501c2c06ed9556fe5b542469，计划18，实际13尝试：12接受、1起飞前失败、5未运行。
heading6轮/3对和force6轮/3对通过，mass尚未飞行，不称18轮完成。首败停批、未自动重试，命令退出1。
231 C++/583 Python、2262冻结资产/构建通过；12个接受轮独立完整回放退出0，指标值一致（counts键顺序例外）。
26份ULog及819原始工件指纹见summary和original_artifacts.sha256；原索引SHA19581c59977072889a4449308e88f148645a1be2fe558152ff70705ae04a0684。
原日志在外部V08/pilots01，未删除。EEPROM恢复06a022de820f43ba6b9559c90da62d16326de448d19a19254c268c328fa113fc。
mass失败原因及零飞行模型链审计见../offline_failure03；失败不改判。V08仍未验收，不push、不正式试验。
