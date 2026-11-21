# video-timestamp-jitter

## 题面

弱网下接入抖动缓冲后，画面还是卡顿、偶发倒退播放：抖动估计直接拿相邻到达差当抖动、没有按 RTP 时间戳推进量归一；重排依赖不稳定的 sort，同 seq 的先后被打乱；插入忽略 target_delay，包还没到播放点就提前出队；播放遇到缺包直接跳过，时间轴被压缩；自适应延迟不钳制，抖动小时延迟被算到 0；16 位序号回绕不检测，65535 之后整段被判成旧包丢弃；时间戳回退不报错，播放位置倒退；重复 seq 不去重，同一个包被播放多次；批量处理共用一份缓冲，不同流之间互相串包；clock=0 不校验，归一化时直接除零。jitter/buffer.py 是核心，tests/test_buffer.py 15个红。要修的是：抖动估计按 RTP 时间戳归一、重排稳定且跨 16 位回绕保序、插入遵守 target_delay、缺包以 None 占位、自适应延迟钳制到 [min_delay, max_delay]、回绕检测、时间戳回退校验、重复 seq 去重、批量每流独立缓冲、clock 非正抛 JitterError。

## 运行方式

在仓库根目录执行：

```bash
python -m pytest tests -q
```

初始失败环境必须恰好是 `15 failed`，不能出现 collection、import 或 syntax error：

```text
15 failed
```

时间模型全部显式传入，不 sleep、不取当前时间、不使用随机数：`arrival` 是毫秒，`ts` 是 90 kHz RTP tick（1 tick = 1/90000 秒），`clock` 是每秒 tick 数（视频为 90000）。只允许标准库（`collections`、`math`）与 pytest，离线运行。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 音视频处理 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 约束

- `tests/test_buffer.py` 不可修改：15 个测试是验收标准，只能改 `jitter/buffer.py`（必要时可维护 `jitter/__init__.py` 的导出）。
- 保留 8 个公开函数的签名与 `{"seq", "ts", "arrival"}` 包结构，异常类为 `JitterError`。
- 实现必须确定性、可离线复现；不要引入第三方依赖、不要联网、不要读取真实时钟。
