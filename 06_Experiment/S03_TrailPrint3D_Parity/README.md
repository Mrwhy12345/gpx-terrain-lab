# S03：TrailPrint3D 三环境对照实验

启动日期：2026-08-07

## 实验目标

用同一份星溪徒步 GPX 和同一组 TrailPrint3D 参数，对比三种环境是否能够生成**几何等价、装配等价、可切片等价**的 3MF：

1. macOS + Blender 图形界面（GUI）
2. macOS + Blender 纯命令行（Headless CLI）
3. Linux + Blender 纯命令行（Headless CLI）

核心问题：

> 图形界面是否可以被后台脚本替代，以及 Linux 是否可以作为未来 Web 服务的生成后端。

## 实验编号与顺序

| 实验 | 环境 | 主要验证 | 状态 |
|------|------|----------|------|
| **E101** | macOS Blender GUI | 建立人工操作基准 | ⬜ 待开始 |
| **E102** | macOS Headless CLI | 验证 TrailPrint3D 是否依赖 GUI | ⬜ 待开始 |
| **E103** | Linux Headless CLI | 验证跨平台后台部署 | ⬜ 待开始 |
| **E104** | 三方对比 | 自动检查模型和切片结果 | ⬜ 待开始 |

先完成 E101，再做 E102。只有 E102 成功，才进入 E103。

## 固定变量

- 同一份星溪 GPX（SHA-256 校验）
- 同一 Blender 版本（5.2.0 LTS）
- 同一 TrailPrint3D 版本（3.1.2）
- 同一参数组（见 `config/job.json`）
- 同一 DEM API

## 等价性分级

- **PASS**：打印等价。几何指标在容差内，切片结果基本一致。
- **PASS WITH DIFFERENCES**：存在顶点数、三角化或文件大小差异，但尺寸、体积和切片结果等价。
- **FAIL**：对象缺失、明显偏移、尺寸不同、轨迹错误或无法切片。

## 3MF 处理边界

实验分两层：

**第一层：Blender 生成层** — 三种环境对比 `.blend`、地形模型、轨迹模型的几何。

**第二层：3MF 装配层** — 由同一台 Mac、同一个 Bambu Studio 手工导入三组输出，分别保存为 3MF。

后续再单独研究 Bambu Studio / OrcaSlicer 命令行自动化。
