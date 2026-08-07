# E102：macOS Headless CLI

状态：⬜ 待开始

## 前置条件

E101 完成，参数已锁定。

## 目标

验证 TrailPrint3D 核心生成流程能否在 `blender --background` 模式下运行。

## 分两阶段

### E102-A：插件加载测试

- [ ] Blender 后台启动成功
- [ ] 插件能注册
- [ ] 插件属性能读取
- [ ] 能保存测试 `.blend`
- [ ] 没有 `VIEW_3D`、`context.area` 等错误

### E102-B：完整生成

- [ ] 脚本加载 GPX
- [ ] 写入与 E101 相同的参数
- [ ] 调用生成逻辑
- [ ] 保存 `.blend`
- [ ] 导出地图和轨迹
- [ ] 输出日志

## 预期命令形式

```bash
blender \
  --background \
  --factory-startup \
  --python-exit-code 1 \
  --python scripts/trailprint_worker.py \
  -- config/job.json
```

## 失败分类

| 失败类型 | 含义 |
|----------|------|
| 插件无法注册 | 插件初始化依赖 GUI 或环境 |
| Operator `poll()` 失败 | 依赖 Blender 图形上下文 |
| 能生成但不能导出 | 导出逻辑需单独调用 |
| 输出位置错误 | 活动对象、Collection 或变换未设置 |
| 结果和 GUI 不一致 | 参数没有完整映射或存在隐藏状态 |

## 必须保存

| 文件 | 说明 |
|------|------|
| `env/` | 同 E101 |
| `scripts/trailprint_worker.py` | 自动化脚本 |
| `logs/` | 完整运行日志 |
| `source/xingxi_cli.blend` | Blender 源文件 |
| `output/` | 地图、轨迹模型 |
| `notes.md` | 运行耗时、异常记录 |

## 验收标准

- [ ] 后台进程退出码为 0
- [ ] 输出对象数量与 E101 一致
- [ ] 地图和轨迹尺寸一致
- [ ] 能在 Bambu Studio 中正常导入
- [ ] 不需要人工打开 Blender 窗口
- [ ] 生成过程有完整日志
