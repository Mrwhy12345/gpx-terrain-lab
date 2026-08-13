# 三路线全面回归测试报告

- 结果：**PASS_WITH_WARNINGS**
- 时间：2026-08-13T16:52:29.768853+08:00
- 范围：GPX 输入、Web 任务溯源、5+1、三色地形、轨迹、水系、四件同盘、颜色、Z/打印盘、Blender 与三机位。

## 汇总

| 路线 | 点数/轨段 | 高程倍率 | 水系组件 | 四对象 | 最终三机位 | 结果 |
|---|---:|---:|---:|---|---|---|
| 2025-02-23 从化星溪线 | 878/1 | 1.8 | 2 | True | True | **PASS** |
| 广州大夫山环穿画马（石马山～三乌岗～石马山）20251222+20260110（合并） | 1417/3 | 1.8 | 13 | True | True | **PASS_WITH_WARNINGS** |
| 新兴水源山—孖山(风车山)环线 | 983/1 | 1 | 3 | True | True | **PASS** |

## 自动检查明细

### 2025-02-23 从化星溪线

- 对应任务：`WEB_20260813_142826_2025-02-23_从化星溪线`
- PASS：gpx_two_steps_profile
- PASS：input_hash_matches_job
- PASS：five_plus_one
- PASS：release_qa
- PASS：four_objects
- PASS：trail_one_piece
- PASS：final_three_views
- PASS：blender_materials
- PASS：water_components_target_max_5
- ADVISORY：physical_print_assembly_not_automated

### 广州大夫山环穿画马（石马山～三乌岗～石马山）20251222+20260110（合并）

- 对应任务：`WEB_20260813_151247_广州大夫山环穿画马_石马山_三乌岗_石马山_20251222_20260`
- PASS：gpx_two_steps_profile
- PASS：input_hash_matches_job
- PASS：five_plus_one
- PASS：release_qa
- PASS：four_objects
- PASS：trail_one_piece
- PASS：final_three_views
- PASS：blender_materials
- WARNING：water_components_target_max_5
- ADVISORY：physical_print_assembly_not_automated

### 新兴水源山—孖山(风车山)环线

- 对应任务：`WEB_20260813_141754_新兴风车山环线`
- PASS：gpx_two_steps_profile
- PASS：input_hash_matches_job
- PASS：five_plus_one
- PASS：release_qa
- PASS：four_objects
- PASS：trail_one_piece
- PASS：final_three_views
- PASS：blender_materials
- PASS：water_components_target_max_5
- ADVISORY：physical_print_assembly_not_automated

## 问题分级

- **BLOCKER（阻断）**：核心几何、5+1、四对象、轨迹连续性、颜色/材质或仿真证据错误；必须修复。
- **WARNING（警告）**：结果可用，但安装、强度或复杂度未达目标；允许当前阶段交付并记录风险。
- **ADVISORY（建议）**：审美、减件和效率优化，不影响当前交付。

## 事实、假设与边界

- 事实：三条输入按 SHA-256 匹配各自最新完整 Web 任务，不按文件名猜测。
- 事实：用户已在 Bambu Studio 手动打开三条路线的四件同盘 3MF，并确认可用。
- 假设：这些 GPX 均代表当前标准的“两步路”导出输入。
- 边界：自动测试不能替代耗材、切片参数、打印强度和实际装配真机验收。

## 结论

当前三路线通用回归结论：**PASS_WITH_WARNINGS**。只有 BLOCKER 阻止当前阶段发布；WARNING 与 ADVISORY 进入后续优化清单。
