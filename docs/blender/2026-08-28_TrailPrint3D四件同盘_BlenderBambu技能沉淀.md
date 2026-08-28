# 2026-08-28 TrailPrint3D 四件同盘（Blender + Bambu Studio）技能沉淀

> **目的**：让新模型 / 新成员可复现地从零学会：用 TrailPrint3D 插件生成多色 3D 打印纪念沙盘的「4 件同盘」，并正确导入 Bambu Studio 切片。
> **对象**：徒步 GPX → 沙盘地形 / 底座 / 轨迹 / 水系 四个独立实物件，同板面分摆，多色打印。
> **前置**：Blender 5.2 LTS、TrailPrint3D 插件 v3.2.1（作者 EmGi3D）、Bambu Studio 切片、Clonephaze `io_mesh_3mf` 扩展。

---

## 一、学习路径（新模型怎么学）

按此顺序学，最快形成正确心智模型，避免「凭想象拼装」：

1. **官网文字教学**（先建立概念，不碰代码）：
   - 官网 `https://trailprint3d.com/` 子页：`howto.html` / `examples.html` / `filaments.html` / `changelog.html` / `download.html`
   - YouTube 频道 `@EmGi_` 的 howto 内嵌视频
2. **读插件源码**（拿真参数，不猜枚举）：
   - `TrailPrint3D/props.py`：所有 `EnumProperty` / `IntProperty` / `FloatProperty` 的真实定义与默认值
   - `TrailPrint3D/utils/generation.py`：地形/底座/文字/轨迹/水系的对象创建与导出逻辑
   - `TrailPrint3D/export.py`：3MF 导出与分组逻辑
   - `TrailPrint3D/threemf_discovery.py`：3MF addon 发现机制
3. **跑一次快速预览**（优先 subdiv 5，约 18 秒）验证结构与颜色，再上 subdiv 8 高精度成品。
4. **对照仓库样例**（`blender-lab/reference/星溪线V007_github/`）逐字核对颜色与分件，不靠猜。

> ⚠️ 铁律：**任何枚举值、默认参数、颜色、事件都以源码 / 样例文件为准**，不凭印象推断。`bpy_struct attr = val` 报枚举报错时，去 `props.py` 查合法枚举。

---

## 二、核心概念：4 件同盘（最重要的纠偏）

**「4 件同盘」= 同板面分摆的 4 个独立实物件，不是叠装、不是拼成一个组合体。**

| # | 件 | 说明 |
|---|-----|------|
| 1 | **沙盘（地形）** | 六边形地形网格，绿主 + 棕地块 + 灰高地，带水体/元素安装槽（cutout） |
| 2 | **地盘（底座/底板）** | 底板 + 标题/文字刻字（可加 SVG 竹林 Logo） |
| 3 | **轨迹** | 红色独立安装件，Z 形路径 |
| 4 | **水系** | 蓝色独立安装件，河流/湖泊曲段 |

**为什么容易做错**：样例同盘 3MF 里通常有 7 个 component（地形 3 色拆 3 块 + 底座本体/文字拆 2 块 + 轨迹 + 水系 = 7）。这些是切片软件里**为了按层打印拆开的色块**，**逻辑上仍是 4 件**。不要据此误判成「7 个件」或「叠装组合体」。

**交付形态**：地形、底座、轨迹、水系这 4 件**分开摆放**在同一打印板上，不是上下叠在一起。

---

## 三、插件原生生成机制（关键参数）

### 3.1 Shape 与文字地盘

`shape`（合法枚举，`props.py`）：
```
HEXAGON / SQUARE / CIRCLE / OCTAGON / ELLIPSE / HEART
```

`shapeTextStyle` 是**动态枚举**（随 shape 变化），HEXAGON 的合法项：
```
NONE / INNER TEXT / OUTER TEXT / FRONT TEXT / SHELL(Premium)
```

✅ 文字地盘正确写法（**不能写成 `'HEXAGON OUTER TEXT'` 字符串**，会报枚举报错）：
```python
p.shape = 'HEXAGON'
p.shapeTextStyle = 'OUTER TEXT'   # 带文字地盘(backplate)
```
> `shapeTextStyle` 赋值仍可能失败，因为它是动态 EnumProperty。稳妥做法是赋值后捕获异常并打印 `shapeTextStyleCache` 确认。

### 3.2 排版文字字段（`props.py`）

| 属性 | 说明 | 可用占位符 |
|------|------|-----------|
| `titlefield` | 标题 | `{name} {length} {elevation} {date} {speed} {scale}` |
| `textfield1..5` | 下方文字行 | 同上 |
| `textSize` | 字号（默认 5） | — |
| `textFont` | 字体路径 | 如 `/System/Library/Fonts/Hiragino Sans GB.ttc` |
| `plateThickness` | 底板厚度（默认 5mm） | — |

### 3.3 轨迹与元素（独立件）

| 属性 | 值 | 说明 |
|------|-----|------|
| `singleColorMode` | `True` | 轨迹全单色独立件 |
| `elementMode` | `'SINGLECOLORMODE_REMESH'` | 元素单色独立件 + 沙盘留槽 |
| `elementMode` 其它 | `'PAINT'`（画上）/ `'SEPARATE'`（独立件） | 按需选 |

### 3.4 水系三开关（全开才拉 OSM 水系）

```python
p.col_wPondsActive        = True   # 池塘
p.col_wSmallRiversActive  = True   # 小河
p.col_wBigRiversActive    = True   # 大河
```

### 3.5 网格精度

- `num_subdivisions`：**5**（快速预览，约 18s）/ **7**（约 49K 顶点地形）/ **8**（高精度，约 194K 顶点，约 4 倍于 subdiv7，推荐成品）
- subdiv 越高地形越细腻，但生成越慢；预览用 5，成品用 8。

---

## 四、产物对象与颜色（插件原生材质）

一次生成产出的对象命名（`<name>` = `trailName`）：

| 对象 | 材质 | 颜色 |
|------|------|------|
| `<name>` | `BASE` | 地形 **绿** (0.05, 0.70, 0.05) |
| `<name>_Plate` | `BLACK` | 地盘/底座 **黑** (0,0,0) |
| `<name>_Text` | `WHITE` | 文字/Logo **白** |
| `<name>_Trail` | `TRAIL` | 轨迹 **红** (1,0,0) |
| `<name>_WATER` | `WATER` | 水系 **蓝** (0,0,0.8) |

> 渲染用 Workbench 引擎按材质颜色显示最稳（EEVEE 易空白）。用 Principled BSDF 的 `Base Color` 读取色值即可核对。

---

## 五、完整参数基线（引用真机验证）

沿用以真机打印 PASS 的基线（详见 `07_Knowledge/Conclusions/TrailPrint3D_真机验证参数基线.md`）：

| 参数 | 默认值 |
|---|---:|
| Shape | Hexagon |
| Shape Text | Outer text |
| Object Size | 100 mm |
| Resolution | 8 |
| Elevation Scale | 1.80 |
| Path Thickness | 1.60 mm |
| SingleColorMode Trail | 开启 |
| Scale mode | Map Scale（`FACTOR`） |
| Path Scale | 0.80 |
| Water / Big Rivers / Small Rivers | 开启 |
| River Width | 1.00 |
| Water Threshold | 1.00 |
| 轨迹槽单侧公差 | 0.20 mm |
| 水系槽单侧公差 | 0.25 mm |
| 水系轮廓 XY 单侧加宽 | 0.15 mm |
| 水系局部承力颈宽 | 1.35 mm |
| 水系局部承力颈高 | 0.55 mm |

> 数据一律从 TrailPrint3D 获取（地形高程、水系、森林、城市边界等），后处理只做配色/分层/安装槽/公差/底座/Logo/3MF/QA。不另建 OSM 查询作默认事实源。

---

## 六、Blender 渲染与预览（排错重点）

**问题**：EEVEE 渲染空白（黑图/全灰）。
**原因**：相机没对准物体 + 灯光/裁剪距离问题。

**最稳方案：Workbench 按材质颜色渲染**
```python
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'MATERIAL'   # 按材质颜色
scene.display.shading.show_shadows = False
```
**相机对准 + 裁剪距离 + 灯光（EEVEE 时）**
```python
cam.location = (cx, cy, cz + size*2.5)
cam.rotation_euler = (0, 0, 0)
cam.data.type = 'ORTHO'
cam.data.ortho_scale = size*1.25
cam.data.clip_start = 0.01
cam.data.clip_end = size*20          # 关键：默认裁剪太近会裁掉物体
bpy.ops.object.light_add(type='SUN', location=(cx,cy,cz+size*3))
```
**取物体全局包围盒中心**：遍历所有网格 `o.bound_box` 乘 `o.matrix_world`。

---

## 七、3MF 导出（依赖 Clonephaze）

插件默认走 STL 导出（日志显示 `exporting as STL/OBJ`），**因为找不到 3MF addon**。要带颜色导出，必须安装 **Clonephaze 的 `io_mesh_3mf`** 扩展。

- 发现机制：`threemf_discovery.py` 的 `get_threemf_api()`，三级探测（`driver_namespace` → `importlib` → `addon_utils`）。
- 官方扩展名：`io_mesh_3mf`（不是 `io_scene_3mf`）。
- 安装位置：Blender Preferences → Extensions，或手动放入 `~/Library/Application Support/Blender/5.2/extensions/`。
- 验证：
```bash
# 检查扩展是否可用
/Applications/Blender.app/Contents/MacOS/Blender -b --python-expr "import addon_utils; print([m.__name__ for m in addon_utils.modules() if '3mf' in m.__name__.lower()])"
```
- STL 导出会丢失颜色，仅用于结构/几何预览；**正式交付前必须解决 3MF 导出**。

---

## 八、Bambu Studio 检查

1. **导出预览图**：用 Bambu 打开 3MF（`plate_1_0.png`），看 4 件同盘分摆 + 多色映射。
2. **颜色槽核对**：打开 `project_settings.config`（JSON），读 `filament_multi_colour` 调色板 + `extruder_ams_count` + `print_extruder_id`，确认每个颜色槽对应正确耗材。
3. **下沉检查**：确认无负 Z（`最低点 ≥ 0`），4 件都在打印板面。
4. **分件结构**：`object_1.model` 里的 sub-object（component）数 = 色块数，逻辑上仍对应 4 件。
5. **装配位置**：同盘分摆，不叠装。

---

## 九、常见排错表

| 现象 | 原因 | 解决 |
|------|------|------|
| `attr = val` 枚举报错 | 枚举值不存在 | 读 `props.py` 查合法枚举；`shapeTextStyle` 是动态枚举，不能直接赋复合字符串 |
| 渲染全空白 | EEVEE 相机/裁剪/灯光问题 | 改 Workbench + `color_type='MATERIAL'`；加大 `clip_end = size*20` |
| 生成假死（CPU 0%） | Overpass API 抖动 | 探活 `overpass-api.de` 的 `http_code`，主源 3 次全通才跑；1 次失败可换备用源 |
| 导出走 STL 无颜色 | 缺 Clonephaze `io_mesh_3mf` addon | 安装扩展后重跑，确认 `Successfully exported to: xxx.3mf` |
| 底座颜色/分件不合预期 | 只看了 `model_settings.config` 的 part→extruder 映射 | 打开 `project_settings.config` 读真实调色板 + 打开 3MF 看视觉 |
| 误做成 7 件/叠装 | 没理解 component=色块 | 记住：7 component 逻辑上仍是 4 件，同板面分摆非叠装 |

---

## 十、后处理（竹林 Logo / 磁铁孔）

- **竹林 Logo**：`blender-lab/reference/星溪线V007_github/bamboo_logo.svg`（单色线描竹林徽章，双竹竿+放射竹叶+竹节分叉，底部「星溪竹海」四字）。SVG→PNG 用 macOS 自带 `qlmanage`（本地无 rsvg-convert/cairosvg/inkscape）。
- **磁铁孔**（用户拍板）：4 孔 / 直径 6mm / 深 3mm / 距角 15mm（底座四角各 1）。
- 设计基准：单色线描，只做正面/底部可打印徽章，不做复杂浮雕。

---

## 十一、可复用脚本

- 生成脚本参考：`blender-lab/scripts/pipeline007.py`（`./pipeline007.py <gpx> <项目名>`，产物至 `blender-lab/output/pipe_<项目名>/`）。
- ⚠️ pipeline007 是**脚本拼装版（7 件套）**；用户已确认改为**插件原生机制生成 4 件同盘**（见 §二/§三），方向以此文档为准。
- 工具脚本：`07_Knowledge/tools/*.py`（`build_*.py` 建几何 / `add_*.py` 后处理 / `build_bambu_*_3mf.py` 拼 Bambu 3MF / `audit_*.py` QA）。
- 关键脚本速查：
  - `build_bambu_one_plate_3mf.py`／`build_bambu_job_3mf.py`：从预定位 STL 拼 Bambu 兼容多件 3MF
  - `add_base_bottom_logo_inlay.py`：底座底部 Logo 嵌片
  - `add_trail_insert_and_groove.py`：轨迹平底嵌件 + 开槽
  - `build_water_inserts_and_grooves.py`：水系嵌件 + 开槽

---

## 附：本次验证记录

- 2026-08-28：用插件原生机制（`HEXAGON + OUTER TEXT` + `singleColorMode` + `elementMode=SINGLECOLORMODE_REMESH` + 水系三开关全开）一次生成产出 5 对象（地形/_Plate/_Text/_Trail/_WATER），subdiv 5 约 18 秒，水系从 Overpass 拉取成功（`WATER loop 1/1`, 5 parts）。
- 颜色核验（原生材质）：地形绿 `(0.05,0.70,0.05)` / 底座黑 `(0,0,0)` / 轨迹红 / 水系蓝 / 文字白。**底座为黑**（用户强调）。
- 渲染：Workbench 按材质颜色成功出图（4 件同盘分摆，黑底绿地形红轨迹蓝水系 + 刻字「星溪线4件预览 9.52km 671.01m 2025-02-23」）。
- 待办：装 Clonephaze `io_mesh_3mf` → 导出带颜色 3MF；上 subdiv 8 + 竹林 Logo + 磁铁孔；打 ZIP + SHA256SUMS 归档 `交付物/`。
