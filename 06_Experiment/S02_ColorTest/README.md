# S02_ColorTest：GPX地形模型多色打印验证

**日期：2026-08-07**
**状态：✅ 核心链路验证完成，Multi模式待验证**

## 实验目标

验证完整流程：

```
真实徒步 GPX → TrailPrint3D → 多对象模型 → Bambu Studio → 多色打印
```

重点验证：

1. OSM水体是否可以加入地形模型
2. 中文文字是否可以正常生成
3. 地形、水体、森林、轨迹是否可以分色导出
4. 多色打印结构是否满足FDM打印要求

---

## 一、实验环境

### Hardware

| 项目 | 配置 |
|------|------|
| 打印机 | Bambu Lab H2C |
| 喷嘴 | 0.4mm |
| AMS | 2套（最多8色） |
| 电脑 | Mac mini (Apple Silicon) |

### Software

| 软件 | 版本/用途 |
|------|-----------|
| Blender | 5.2 LTS |
| TrailPrint3D | v3.2.1 |
| Bambu Studio | 切片验证 |

---

## 二、实验输入

- GPX：星溪徒步（真实徒步轨迹）
- OSM数据：Water & Ocean、Forest

---

## 三、实验过程与发现

### 1. 中文字体测试

**问题**：默认字体无法显示中文标题"星溪徒步"

| 字体 | 结果 |
|------|------|
| Arial.ttf | 无报错，但中文缺失 |
| GB18030 | 不支持 Blender 加载 |
| STHeiti Medium.ttc | 无报错，但中文缺失 |
| STHeiti Light.ttc | 无报错，但中文缺失 |
| Songti.ttc | ✅ 正常显示 |

**最终采用**：`/System/Library/Fonts/Supplemental/Songti.ttc`

**字体代码定位**：通过搜索插件源码，字体参数来自 `props.textFont`，说明 TrailPrint3D 支持自定义字体路径。

### 2. 多颜色模型生成

测试 Single-Color mode，成功生成独立对象：

- Terrain.stl
- WATER.stl
- FOREST.stl
- Trail.stl

全部成功导入 Bambu Studio。

### 3. 关键发现1：TrailPrint3D已自动生成水体开槽

**之前误认为**：WATER需要手工Boolean开槽

**实际发现**：TrailPrint3D已经处理。Blender中 Terrain + Water 已经形成嵌入水槽结构。

**结论**：无需额外Boolean操作。

### 4. 关键发现2：Bambu Studio浮空报警来自独立STL识别

**现象**：WATER.stl 存在悬空区域报警

**原因**：不是模型错误。切片器看到 Terrain.stl 和 WATER.stl 两个独立对象，不知道 WATER 属于 Terrain 嵌入件。

**解决方向**：需要将多对象保持空间关系导入（作为单一对象的多部件），或使用 Multi 模式导出。

### 5. Post Process 面板确认

TrailPrint3D 的 Post Process 功能主要包括：

| 功能 | 作用 |
|------|------|
| Color Mountains | 山体颜色分层 |
| Contour Lines | 等高线 |
| Magnet Holes | 磁吸孔 |
| Dovetail Cutouts | 燕尾拼接 |
| Bottom Mark | 底部文字 |
| SVG/Text Import | 导入SVG文字 |

**结论**：Post Process 没有"水体下沉/嵌入"功能，几何嵌入已在生成阶段自动完成。

---

## 四、Blender Boolean 操作（手动修正方案）

对于 Single-Color 模式导出的独立 STL，如需在 Blender 中手动创建水槽：

1. 选择 WATER → Shift+D 复制 → 改名 WATER_CUTTER
2. 给 WATER_CUTTER 添加 Solidify Modifier（厚度2-3mm）
3. 选择 Terrain → 添加 Boolean Modifier（Intersect, Object: WATER_CUTTER）
4. 应用 Boolean → 删除 WATER_CUTTER

森林同理，建议嵌入 0.3-0.5mm。

---

## 五、实验结论

### 已完成

| 项目 | 状态 |
|------|------|
| GPX导入 | ✅ |
| OSM水体获取 | ✅ |
| 中文标题生成 | ✅（Songti.ttc） |
| Single-Color模式多对象导出 | ✅ |
| TrailPrint3D自动水体开槽 | ✅（重要发现） |
| Bambu Studio导入验证 | ✅ |

### 未完成

| 项目 | 状态 |
|------|------|
| Multi模式导出验证 | ⬜ 下一步 |
| 水体嵌入精度验证 | ⬜ |
| 森林嵌入验证 | ⬜ |
| 实体打印验证 | ⬜ |

---

## 六、阶段性认识

本实验完成了从"地图数据"到"可打印多色地形模型"的核心链路验证。

关键转变：

- **以前**：AI生成模型 → 打印
- **现在**：真实世界数据 → 多色制造

下一阶段重点：**优化数据结构，而不是继续建模。**

---

## 七、下一步

1. 切换 Multi 模式重新生成，验证是否能直接输出多颜色模型
2. 验证 Multi 模式下 AMS 分色是否正常
3. 完成首件实体打印验证
