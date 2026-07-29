# GPX Terrain Lab

把徒步 GPX 转换成经过 GIS 核验、可在 Blender 中预览、可多色 3D 打印的纪念沙盘。

## 产品目标

输入一个 GPX，经过 DEM/OSM、QGIS 空间处理、地图人工核验和 Blender 几何生成，
输出职责独立且保持同一装配坐标的：

- 地形 3MF；
- 底座 3MF；
- 徒步轨迹 3MF；
- 河流水体 3MF；
- 可选同盘 3MF；
- Blender 设计预览与 QA 报告。

## 当前状态

星溪线 S02 / SYS01 V007 已完成数字封版，正在进行首件打印验收。单案例核心链路已
验证，下一阶段是统一 `job.json`、单命令流水线和第二条 GPX 回归。

## 文档入口

- [产品目标](00_Project/对外系统目标.md)
- [后续 Agent 交接总览](00_Project/后续Agent交接总览_2026-07-29.md)
- [团队协作规范](AGENTS.md)
- [低 Token 复用流程](07_Knowledge/Conclusions/徒步地形模型_低Token复用流程.md)
- [水体获取复盘](07_Knowledge/Conclusions/水体获取失败与成功复盘.md)

## 代码

可复用工具位于 `07_Knowledge/tools/`。当前工具覆盖 GPX、OSM 水体、空间筛选、
Blender 建模、3MF 封装、颜色映射、坐标修复和发布 QA。

## 数据与隐私

公开仓库不包含真实 GPX、精确路线坐标、密钥、3MF/Blend/STL 成果或实验缓存。
高德地图仅用于在线人工视觉核验，不作为模型数据源。

## 开发路线

1. 实体打印验收；
2. 参数化 `job.json`；
3. 单命令、可重试流水线；
4. 第二条路线无需改代码生成；
5. 本地优先 Web 工作台；
6. 五条路线数字回归、三次实体打印后再评估托管服务。
