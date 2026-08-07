# 参数基准说明

更新日期：2026-08-07

## 选择原则

第一轮不追求漂亮，追求稳定和快速。先用低分辨率验证流程跑通，再逐步提高。

## 参数说明

| 参数 | 基准值 | 原因 |
|------|--------|------|
| Shape | Square | 几何最简单 |
| Object Size | 100 mm | 视频中有明确参考 |
| Resolution | 3 | 快速验证（每提升1级，点数约增加3倍） |
| Elevation Scale | E101确定后锁定 | 星溪线可能需要适度夸张 |
| Path Thickness | 固定值 | 三组必须一致 |
| Path Scale | 1.0 | 避免额外裁剪变量 |
| Override Path Elevation | 开启 | 避免 GPX 高程与 DEM 不一致 |
| Fixed Elevation Scale | 固定开或关 | 三组必须一致 |
| Min Thickness | 固定 | 保证可打印 |
| Single Color Mode | 关闭 | 首轮先验证标准多对象模式 |
| Include Elements | 全部关闭 | 首轮不加入 OSM 水体、森林 |
| DEM API | OpenTopoData | 固定一个，避免数据源变化 |

## 锁定流程

1. E101 在 GUI 中调整 Elevation Scale 到满意
2. 将最终值写入 `job.json`
3. E102、E103 读取同一个 `job.json`，不再调整
