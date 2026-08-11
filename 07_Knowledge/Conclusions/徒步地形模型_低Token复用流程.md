# 徒步地形模型低 Token 复用流程

用途：下一条徒步路线直接复用 S02 的已验证方法，减少重复探索、长日志读取和
反复修复 3MF。

项目角色、图标、文件责任和模型切换规则统一登记在根目录 `AGENTS.md`。开始任务
时先按其中的 🦁/🐒/🐗/🐾/🐦 角色路由，再执行本流程。

TrailPrint3D 的默认真机参数以
`07_Knowledge/Conclusions/TrailPrint3D_真机验证参数基线.md` 为唯一基线。

## 一、启动时只提供这些输入

1. GPX 文件路径；
2. 路线名称和日期；
3. 成品尺寸与形状；
4. 目标打印机、喷嘴和耗材数量；
5. 是否需要水体、道路、村庄、起终点、磁铁底座；
6. 一个新的实验编号，例如 S03。

## 二、固定决策，除非用户明确修改

- 坐标：WGS 84 输入，局部米制坐标计算；
- 地形、水、森林、城市等沙盘事实数据：统一由 TrailPrint3D 获取；
- 默认尺寸/精度：六边形、100 mm、Resolution 8、Elevation Scale 1.80；
- 默认轨迹：Path Thickness 1.60 mm、Path Scale 0.80、SingleColorMode Trail；
- 地形边界：从最终地形 Mesh 精确提取；
- GPX 距离：逐段 Haversine；
- 水体事实源：TrailPrint3D 原生 OSM WATER 查询，禁止先按距轨迹距离删水；
- 默认水体参数：Water / Big Rivers / Small Rivers / Include Ocean 全开；
- River Width：1.00；Water Threshold：1.00；
- Min Island Area：2.00；Coastline Simplify：0.100；
- 水体线宽：以 TrailPrint3D River Width 1.00 为事实源，打印后处理不得改变水网数量；
- 水体顶部：高出地形 0.36 mm；
- 水体嵌入：0.18 mm；
- 面状水体阶段性门槛：0.50 mm² 模型面积；
- 文字：生成后转网格、体素封闭，再按最终网格包围盒居中；
- 三边文字：从基座 Mesh 支撑边自动求中点，禁止手填 XY；
- 版本：任一零件变化，完整三件套统一升版；
- 原始数据永不覆盖。

## 三、最短执行链

1. 读取 GPX，输出点数、长度、异常跳点；
2. 生成地形并冻结模型 XY 边界；
3. TrailPrint3D 按真机基线生成地形、轨迹及所需元素，并保存原生对象与报告；
4. 代码只做最终沙盘边界裁剪、几何有效性和打印分类；距轨迹距离仅用于审计，不用于删除沙盘内水系；
5. 对沙盘范围内完整水网做地图核验；仅删除明确错误、越界或无法打印的噪声；
6. Blender 生成地形、水体、轨迹、底座和文字；
7. 文字按最终基座几何自动居中；
8. 输出独立同原点零件；
9. 封装完整版本号一致的 3MF 套装；
10. 检查 ZIP、零件数、耗材、负 Z、非流形边和不变件哈希；
11. 生成一张俯视图、一张斜视图；
12. 写阶段 checkpoint 和 SHA-256 清单后封版。

## 四、优先复用的工具

- `tools/generate_job_trailprint.py`（原生完整水网）
- `tools/inspect_trailprint_native_water.py`
- `tools/analyze_water_proximity.py`（只审计，不作为默认删除条件）
- `tools/audit_s02_water_printability.py`
- `tools/extract_trailprint_boundary.py`
- `tools/build_blender_water_geometry.py`
- `tools/build_three_band_print_model.py`
- `tools/build_trail_insert_and_groove.py`
- `tools/add_terrain_seat_recess.py`
- `tools/update_three_edge_labels.py`
- `tools/render_three_edge_labels_top.py`
- `tools/export_three_physical_pieces.py`
- `tools/replace_bambu_3mf_part_from_stl.py`
- `tools/set_bambu_3mf_part_extruders.py`

## 五、每阶段只保留一个续做入口

阶段总结必须包含：

- 当前目标；
- 当前完整版本；
- 不可变输入；
- 已确认事实；
- 仍在使用的假设；
- 已完成输出；
- 未决项；
- 下一步；
- 若修改应升到哪个版本。

新任务开始时先读 checkpoint，不再扫描全部历史日志。

## 六、预计 Token 节省

S02 的高消耗主要来自首次探索：

- 反复定位 Blender/3MF 坐标；
- 发现 3MF 内有两套零件变换；
- 手工调整文字位置；
- 多次确认水体边界和打印门槛；
- 从大量零散文件恢复阶段状态。

复用本流程后，同类路线若需求稳定，预期可以把完整制作过程压缩到原探索过程的
约 30%～50%。单独的三边文字居中调整，可从本次约 12k～18k 的工作量降低到
约 3k～6k。
