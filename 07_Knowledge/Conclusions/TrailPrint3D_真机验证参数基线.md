# TrailPrint3D 真机验证参数基线

状态：用户已打印测试通过，作为 GPX Terrain Lab 默认工程基线。除非客户明确修改，不再凭模型推测替换。

## 数据来源原则

- 地形高程和沙盘元素数据统一从 TrailPrint3D 获取。
- 水体、森林、城市边界、绿地、农田、碎石坡、冰川等，均使用 TrailPrint3D 对应开关和阈值。
- GPX Terrain Lab 后处理只负责：配色、分层、打印筛选、安装槽、公差、轨迹优先、底座、Logo、3MF 与 QA。
- 不得另建 OSM 查询作为默认事实源；外部查询只能用于审计、故障诊断或地图交叉核验。

## 截图一：形状、地形与轨迹

| 参数 | 默认值 |
|---|---:|
| Shape | Hexagon |
| Shape Text | Outer text |
| Object Size | 100 mm |
| Resolution | 8 |
| Elevation Scale | 1.80 |
| Path Thickness | 1.60 mm |
| SingleColorMode Trail | 开启 |
| Scale mode | Map Scale (`FACTOR`) |
| Path Scale | 0.80 |

## 截图二：元素与水系

| 参数 | 默认值 |
|---|---:|
| Element handling | Single-Color mode (`SINGLECOLORMODE_REMESH`) |
| Water | 开启 |
| Big Rivers | 开启 |
| Small Rivers | 开启 |
| River Width | 1.00 |
| Water Threshold | 1.00 |
| Include Ocean | 开启 |
| Min Island Area | 2.00 |
| Coastline Simplify | 0.100 |
| Forest Threshold | 10.00 |
| Scree Threshold | 1.00 |
| City Threshold | 1.00 |
| Greenspace Threshold | 1.00 |
| Farmland Threshold | 1.00 |
| Glacier Threshold | 1.00 |

截图中森林、碎石坡、城市、绿地、农田和冰川开关为关闭状态；其阈值作为启用时的经验默认值。是否启用由路线与客户需求决定，但数据仍必须由 TrailPrint3D 获取。

## QA 门槛

- 生成报告必须回写上述实际参数，不能只记录期望值。
- 若后处理再次放大 Z，等于偏离 Elevation Scale 1.80；默认禁止。
- 若轨迹后处理改变宽度，最终值仍必须为 1.60 mm。
- 任一参数偏离时，版本状态必须标记为实验版，不得标记为此基线的封版成果。

