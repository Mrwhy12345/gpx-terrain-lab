# GPX Terrain Lab 本地工作台

本目录是“上传一条 GPX，交付 5 个 3MF + 1 个 Blender 项目”的本地 Web 入口。

当前标准输入为“两步路”导出的 GPX，标准切片与打印软件为拓竹 Bambu Studio。
“通用”是指不同两步路 GPX 共用一套工具链，不表示当前覆盖所有 GPX 方言和所有切片器。

## 启动

双击 `start_local.command`，然后访问：

`http://127.0.0.1:4173/`

也可以在终端运行：

```bash
./start_local.command
```

页面仅在本机读取 GPX，不上传轨迹数据。

## 当前能力（WEB02）

- 本地选择或拖入 GPX；
- 解析轨迹点数并计算近似里程；
- 可视化调整 TrailPrint3D 参数；
- 默认采用真机验证基线：100 mm、Resolution 8、高程倍率 1.80、轨迹宽度 1.60 mm、Path Scale 0.80；
- 固定 TrailPrint3D 为地形、水、森林、城市等工程数据来源；
- 预设 Bambu Studio 配色和 5 个 3MF + 1 个 Blender 输出清单；
- 从页面启动本机 TrailPrint3D + Blender，生成当前 GPX 的真实模型预览图和预览 `.blend`。
- 固定输出装配、顶视、侧视三个 Blender 仿真机位；
- 对任意 GPX 建立独立任务，运行路线无关的 TrailPrint3D → Blender → Bambu 流水线；
- 每次上传均新建任务并从当前 GPX 实时生成；包括星溪在内均禁止跨任务复用封版成品或几何；
- 自动生成 5 个 3MF + 1 个 Blender，并检查 3MF 容器、平台边界、负 Z、文件头与 SHA-256；
- 支持六件逐项下载、完整 ZIP 下载和刷新后恢复最近成果。

## 当前边界

WEB02 已接入通用最终构建器。每次仿真都会新建独立 `08_Jobs/WEB_*`，不覆盖历史成果；流水线按阶段复用已完成产物，失败时保留日志并可续跑。若 TrailPrint3D 没有返回可打印水体或源数据异常，系统会明确失败，不伪造水系或交付成功。

## 目录

- `local/`：无依赖静态版本，当前推荐运行入口；
- `app/`：后续服务化使用的 React 页面源稿；
- `start_local.command`：macOS 本地启动脚本。

## 验收口径

1. 页面离线可打开；
2. 未选择 GPX 时不可进入工程步骤；
3. 参数默认值与真机基线一致；
4. 选择 GPX 后显示文件信息，并建立结构化任务；
5. “启动 Blender 仿真”应生成新的 `WEB_*` 任务目录，并将页面草模替换为 Blender 真实渲染；
6. 页面必须明确区分 GPX 快速草模与 Blender 真实模型渲染；
7. 星溪基准及新 GPX 均应生成六个独立下载入口与一个完整 ZIP，全部显示 QA PASS；
8. 所有新任务必须显示 `current-upload-live-generated-pipeline` 来源，不得复用旧任务的 3MF、Blend 或几何；同一任务中断后允许按阶段续跑。
