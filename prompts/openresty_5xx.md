请诊断以下 OpenResty 5xx 告警。

你需要自动调用 tools 收集证据，不要只给可能原因。

重点验证：

1. 是否是 upstream 异常
2. 是否是单机负载问题
3. 是否是网络限流、ENA 超限、TCP 重传或丢包
4. 是否和发布变更有关
5. 是否是 OpenResty 自身异常

你只能使用 ./tools 下的只读 client。

告警内容如下：

```json
{{ALERT_JSON}}
```

请输出完整 Markdown 诊断报告。
