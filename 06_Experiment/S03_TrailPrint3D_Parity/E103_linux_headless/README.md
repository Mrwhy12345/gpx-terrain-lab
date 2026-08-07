# E103：Linux Headless CLI

状态：⬜ 待开始

## 前置条件

E102 成功。

## 目标

验证同一后台脚本能否迁移到 Linux，并为未来 Web Worker 提供依据。

## 环境要求

- 建议先用 Ubuntu 虚拟机或裸机（不急着 Docker）
- 与 Mac 相同的 Blender 主版本和补丁版本
- 相同 TrailPrint3D 插件文件
- 相同 `job.json`
- 相同 GPX
- 相同 DEM API
- 相同脚本版本

## 需要记录的环境信息

| 项目 | 说明 |
|------|------|
| Linux 发行版 | 如 Ubuntu 24.04 |
| 内核 | `uname -r` |
| CPU 和内存 | `lscpu` / `free -h` |
| Blender 安装来源 | 官网下载 / 包管理器 |
| 插件依赖安装方式 | pip / 系统包 |
| 网络请求是否成功 | DEM/OSM API 可达性 |
| 无 DISPLAY 环境是否正常 | 无显卡环境验证 |

## 执行命令

```bash
blender \
  --background \
  --factory-startup \
  --python-exit-code 1 \
  --python scripts/trailprint_worker.py \
  -- config/job.json
```

## 必须保存

| 文件 | 说明 |
|------|------|
| `env/` | 系统信息、版本信息 |
| `scripts/` | 自动化脚本 |
| `logs/` | 完整运行日志 |
| `source/` | Blender 源文件 |
| `output/` | 地图、轨迹模型 |
| `notes.md` | 运行耗时、异常记录 |

## 验收标准

同 E102，另加：

- [ ] 字体、路径和中文文件名是否有问题
- [ ] 无 DISPLAY 环境下能完成全部几何和导出
- [ ] 网络 DEM/OSM 请求成功
