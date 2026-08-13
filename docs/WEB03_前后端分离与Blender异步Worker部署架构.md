# WEB03｜前后端分离与 Blender 异步 Worker 部署架构

日期：2026-08-11  
状态：架构草案，待评审  
前置版本：WEB02 通用 GPX 本地工作台

## 1. 目标

将当前“浏览器、本地 Python、Blender 同机同步运行”的工作台，逐步升级为：

1. 客户只需使用 Web 页面上传 GPX；
2. 客户不需要安装 Blender 或 TrailPrint3D；
3. 服务端保存任务、参数、状态和成果清单；
4. Neo 本地计算节点异步领取任务并调用 Blender；
5. 最终交付 5 个 3MF、1 个 Blender 项目及 QA 清单；
6. 后续可以增加多个 Blender Worker，而不改变前端和工程流水线。

## 2. 当前实现事实

### 2.1 当前组件

| 组件 | 当前实现 | 职责 |
|---|---|---|
| 前端 | `09_WebApp/local/` 静态 HTML/CSS/JS | GPX、参数、预览、下载 |
| 本地 API | `09_WebApp/local/server.py` | 建任务、启动 Blender、返回文件 |
| 任务存储 | `08_Jobs/WEB_*/` | GPX、配置、中间件、报告、成果 |
| 工程内核 | `07_Knowledge/tools/` | TrailPrint3D、Blender、STL、3MF、QA |
| 计算节点 | 当前 Neo | Blender 5.2 + TrailPrint3D |

### 2.2 当前 Blender 调用方式

浏览器不会直接调用 Blender，而是向本地 Python 服务发送 HTTP 请求：

```http
POST /api/generate-preview
Content-Type: application/json
```

Python 服务建立任务目录并执行：

```bash
/Applications/Blender.app/Contents/MacOS/Blender \
  --background \
  --python 07_Knowledge/tools/generate_job_trailprint.py \
  -- 08_Jobs/WEB_xxx
```

参数说明：

- `--background`：无界面运行 Blender；
- `--python`：指定 Blender 内执行的 Python 脚本；
- `--`：后续参数传给脚本；
- `08_Jobs/WEB_xxx`：任务目录，脚本从其中读取 `job.json` 和 GPX。

TrailPrint3D 完成后，再执行三机位渲染：

```bash
Blender \
  --background \
  work/trailprint_source.blend \
  --python 07_Knowledge/tools/render_web_trailprint_preview.py \
  -- work/blender_preview.blend review/blender_preview.json review/blender_preview.png
```

生成最终文件时，Python 服务调用：

```bash
python3 07_Knowledge/tools/run_generic_job_pipeline.py 08_Jobs/WEB_xxx
```

该脚本负责 15 个可恢复阶段，并在需要时反复启动 Blender 后台进程。

### 2.3 当前调用链

```text
浏览器
  ↓ HTTP JSON
本地 server.py
  ↓ 写入
08_Jobs/job_id/input/route.gpx + job.json
  ↓ subprocess
Blender --background
  ↓
TrailPrint3D + Blender 阶段脚本
  ↓
PNG 仿真、5×3MF、1×Blend、QA
  ↓ /generated 与 /downloads
浏览器
```

### 2.4 当前主要限制

- `subprocess.run()` 在 HTTP 请求内同步等待，最长可能达到 7200 秒；
- Web 服务、任务目录和 Blender 必须在同一台电脑；
- 缺少正式任务队列、并发控制、取消和重试机制；
- 浏览器断开不应影响计算，但当前交互容易让用户误以为需要持续保持连接；
- 不适合直接暴露为公网服务；
- 多客户、多 GPX 连续提交时缺少资源调度。

## 3. 目标架构

目标不是简单拆成“前端 + 后端”，而是拆成四个责任边界：

```text
客户 Web 前端
  ↓ HTTPS
业务 API / 控制面
  ├─ 任务数据库
  ├─ 对象存储
  └─ 任务队列
       ↓
Neo Blender Worker
  ↓
Blender + TrailPrint3D + 通用流水线
  ↓ 上传
对象存储 + QA + 状态
  ↓
客户预览与下载
```

### 3.1 Web 前端

只负责：

- 上传 GPX；
- 填写工程参数；
- 选择标题和 Logo；
- 查看任务进度；
- 查看三机位仿真；
- 下载 5+1。

前端不应知道 Blender 安装路径，也不应访问计算节点的本地文件系统。

### 3.2 业务 API

负责：

- 用户和权限；
- GPX 基础校验；
- 创建任务编号；
- 保存标准化 `job.json`；
- 将仿真或最终任务投入队列；
- 返回状态、预览和下载地址；
- 管理任务配额与生命周期。

业务 API 不直接运行 Blender。

### 3.3 Blender Worker

Neo 作为第一个计算 Worker，负责：

1. 主动领取任务；
2. 下载 GPX 和 `job.json`；
3. 创建隔离工作目录；
4. 调用 Blender 后台进程；
5. 按阶段更新状态和日志；
6. 上传 PNG、3MF、Blend、QA；
7. 通知业务 API 任务完成或失败。

Worker 可继续复用现有工程入口：

```bash
python3 07_Knowledge/tools/run_generic_job_pipeline.py /path/to/job
```

因此，前后端分离不需要推倒已经验证的 Blender 工程链。

### 3.4 对象存储

数据库只存元数据，GPX、PNG、3MF 和 Blend 放入对象存储：

```text
jobs/{job_id}/input/route.gpx
jobs/{job_id}/config/job.json
jobs/{job_id}/preview/assembled.png
jobs/{job_id}/preview/top.png
jobs/{job_id}/preview/side.png
jobs/{job_id}/final/01_沙盘地形.3mf
jobs/{job_id}/final/02_底座.3mf
jobs/{job_id}/final/03_徒步轨迹.3mf
jobs/{job_id}/final/04_河流水体.3mf
jobs/{job_id}/final/05_四件同盘.3mf
jobs/{job_id}/final/06_完整设计预览.blend
jobs/{job_id}/review/final_manifest.json
```

## 4. 建议 API

```text
POST /api/v1/jobs                       创建任务
POST /api/v1/jobs/{id}/gpx              上传 GPX
PUT  /api/v1/jobs/{id}/configuration    更新工程/创意参数
POST /api/v1/jobs/{id}/simulate         提交 Blender 仿真
POST /api/v1/jobs/{id}/finalize         提交最终生产
GET  /api/v1/jobs/{id}                  查询任务状态
GET  /api/v1/jobs/{id}/events           SSE 进度事件
GET  /api/v1/jobs/{id}/artifacts        获取成果列表
POST /api/v1/jobs/{id}/retry            从失败阶段重试
POST /api/v1/jobs/{id}/cancel           请求取消
```

创建仿真后应立即返回，而不是等待 Blender：

```json
{
  "job_id": "JOB_20260811_001",
  "status": "QUEUED_FOR_PREVIEW"
}
```

进度查询示例：

```json
{
  "status": "FINAL_RUNNING",
  "stage": "05_water",
  "progress": 42,
  "message": "正在生成水系安装件"
}
```

## 5. 任务状态机

正常流程：

```text
CREATED
→ GPX_UPLOADED
→ QUEUED_FOR_PREVIEW
→ PREVIEW_RUNNING
→ PREVIEW_READY
→ CREATIVE_REVIEW
→ QUEUED_FOR_FINAL
→ FINAL_RUNNING
→ QA_RUNNING
→ READY
```

建议错误状态：

```text
FAILED_GPX
FAILED_TRAILPRINT
FAILED_WATER
FAILED_BLENDER
FAILED_3MF
FAILED_QA
CANCELLED
```

每个错误必须包含：

- 稳定错误码；
- 用户可读说明；
- 当前阶段；
- 日志位置；
- 是否允许自动重试；
- 是否需要人工处理。

## 6. 部署演进路线

### 阶段 A：本地前后端分离

仍然全部运行在 Neo，但先拆清责任：

```text
浏览器前端
  ↓
本地 FastAPI
  ↓
本地任务队列
  ↓
本机 Blender Worker
```

建议目录：

```text
frontend/
backend/
├── api.py
├── models.py
├── job_store.py
├── queue.py
└── artifact_store.py
worker/
├── worker.py
├── blender_runner.py
└── pipeline_adapter.py
```

验收标准：

- HTTP 请求不等待 Blender 完成；
- 浏览器关闭后任务继续；
- 重启 API 后任务状态仍可恢复；
- 同时只允许配置数量的 Blender 任务运行；
- WEB02 的两条 GPX 回归结果不退化。

### 阶段 B：云端前端/API + Neo 异步 Worker

```text
公网 Web/API
  ↓
云端数据库、对象存储、任务队列
  ↓ Neo 主动拉取
Neo Blender Worker
  ↓ 上传成果
云端服务
```

价值：

- 客户不用安装 Blender；
- Neo 不开放入站端口；
- Worker 只主动访问云端；
- 可以约定数小时或次日交付；
- 可控制每日任务量、优先级和 Token 成本。

### 阶段 C：多 Worker

增加多个带 Blender + TrailPrint3D 的计算节点：

```text
队列
├── Neo-01
├── Neo-02
└── 后续计算节点
```

任务按 Worker 状态、Blender 版本、插件版本和资源能力分发。

## 7. Worker 关键约束

- 每个任务必须使用独立工作目录；
- Blender 和 TrailPrint3D 版本必须进入任务事实；
- 任务领取要有租约，Worker 崩溃后任务可重新领取；
- 同一任务阶段需要幂等，已有合格输出可复用；
- 日志持续落盘并上传；
- 只从受控脚本清单调用 Blender，禁止执行客户提供的 Python；
- GPX 原始文件不可覆盖；
- 只有 QA PASS 才能生成正式下载清单。

## 8. 安全与隐私

- GPX 包含精确位置，必须视为个人敏感数据；
- 上传、对象存储和下载均需 HTTPS；
- 下载使用短期签名 URL；
- Worker 使用独立机器凭据，不保存客户账号密码；
- 设置 GPX、中间产物和最终文件的自动过期时间；
- 公网 API 不直接暴露 Blender；
- 文件名、任务编号和路径必须防止路径穿越；
- 对 GPX 大小、轨迹点数和模型运行时间设置上限。

## 9. 技术决策建议

首版推荐：

| 能力 | 建议 |
|---|---|
| API | FastAPI |
| 本地状态 | SQLite |
| 云端状态 | PostgreSQL |
| 本地队列 | SQLite 队列或 Redis |
| 云端队列 | Redis、SQS 或同类托管队列 |
| 对象存储 | S3 兼容存储 |
| 进度 | 轮询起步，后续 SSE |
| Worker | Python 常驻进程 |
| 工程内核 | 保留 `job.json` + `run_generic_job_pipeline.py` |

不建议第一步就更换 Blender 工程内核或重写全部前端。最先解决的应是：

1. 同步 HTTP 调用改为异步入队；
2. Blender 执行从 API 中拆出；
3. 建立状态机、日志和失败恢复；
4. 再迁移到云端控制面。

## 10. 明日评审决策点

1. 阶段 A 是否先全部留在 Neo；
2. 是否接受 FastAPI + SQLite 作为第一版控制面；
3. 第一版任务并发是否固定为 1；
4. 客户文件保留期限；
5. 仿真完成后是否必须经过客户确认才能生成最终 5+1；
6. Neo 拉取任务的频率与每日交付窗口；
7. 云端对象存储和数据库的供应商选择；
8. 创意环节由客户选择、模型自动生成还是人工审核；
9. 无水系任务是允许 4+1、生成空水系说明，还是进入人工复核；
10. 第一版是否只服务单一管理员账号。

## 11. 结论

现有 WEB02 已经把工程内核参数化，并用星溪、大夫山两条 GPX 验证。前后端分离的重点不是重做模型，而是把 `server.py` 中同步启动 Blender 的责任迁移到独立 Worker，并为它增加队列、状态机和对象存储。

建议下一阶段先实施“本地 FastAPI + 本地队列 + Neo Blender Worker”，在保持两条 GPX 回归通过后，再将前端和控制面迁移到云端。
