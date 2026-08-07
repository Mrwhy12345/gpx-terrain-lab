# ROADMAP

更新日期：2026-08-07

## Phase 1：环境验证（2026-08 启动）

目标：验证 TrailPrint3D 是否可以脱离 GUI 运行，为后续 Web 服务奠定基础。

- [ ] E101 — macOS Blender GUI 基准（人工操作）
- [ ] E102 — macOS Headless CLI（验证是否依赖图形界面）
- [ ] E103 — Linux Headless CLI（验证跨平台部署）
- [ ] E104 — 三方对比与等价性结论（PASS / PASS WITH DIFFERENCES / FAIL）

## Phase 2：自动化

- [ ] 统一 `job.json` 参数驱动
- [ ] 单命令流水线 `gpx-build job.json`
- [ ] 自动导出多对象 3MF + manifest.json
- [ ] DEM/OSM 数据缓存

## Phase 3：连接器（Connector）

- [ ] FastAPI Web 接口
- [ ] 任务队列（Redis + Worker）
- [ ] Docker 容器化
- [ ] 文件生命周期管理

## Phase 4：制造与发布

- [ ] AMS 多色分件自动化
- [ ] Bambu Studio 切片参数模板
- [ ] 打印 QA 自动检查
- [ ] MakerWorld 发布打包

## 里程碑记录

| 日期 | 里程碑 | 状态 |
|------|--------|------|
| 2026-07-29 | 星溪线 V007 数字封版 | ✅ 完成 |
| 2026-08-07 | S03 三环境对照实验启动 | 🔄 进行中 |
