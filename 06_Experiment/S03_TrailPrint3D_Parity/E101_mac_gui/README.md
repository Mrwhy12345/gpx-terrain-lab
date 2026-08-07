# E101：macOS Blender GUI 基准

状态：⬜ 待开始

## 目标

建立"人工操作正确结果"，作为后续 E102/E103 的对照基准。

## 输入

- GPX：2025-02-23 从化星溪线
- 参数：见 `../config/job.json`

## 操作步骤

1. 打开 Blender
2. 确认 TrailPrint3D 已启用（Edit → Preferences → Add-ons）
3. 按 `N` 打开 Trail Print 3D 面板
4. 选择星溪 GPX
5. 设置输出目录
6. 按参数表逐项填写
7. 点击 Generate
8. 保存 `.blend`
9. 导出生成的地图和轨迹文件
10. 在 Bambu Studio 中作为单一对象导入
11. 导出 3MF 工程

## 必须保存

| 文件 | 说明 |
|------|------|
| `env/system.txt` | 操作系统、架构 |
| `env/blender_version.txt` | Blender 精确版本 |
| `env/trailprint3d_version.txt` | 插件版本 |
| `env/bambu_version.txt` | Bambu Studio 版本 |
| `screenshots/01_parameters.png` | 参数截图 |
| `screenshots/02_generated_model.png` | 生成结果截图 |
| `screenshots/03_object_list.png` | 对象列表 |
| `screenshots/04_bambu_preview.png` | Bambu 预览 |
| `source/xingxi_gui.blend` | Blender 源文件 |
| `output/map.*` | 地图模型 |
| `output/trail.*` | 轨迹模型 |
| `output/xingxi_gui.3mf` | 3MF 工程 |
| `notes.md` | 生成耗时、异常记录 |

## 验收标准

- [ ] 地形生成成功
- [ ] 路线没有悬空或钻入地下
- [ ] 地图和路线相对位置正确
- [ ] Bambu Studio 可正常切片
- [ ] 无明显非流形、破面或红色异常区域
- [ ] 记录生成耗时和切片耗时
