# 按需扩展

真实需求触发且选型确认后，才新增对应依赖和目录。

- 认证实现前确认身份来源、Token/Session 传输、有效期、撤销、授权模型和客户端类型。
  优先复用已有身份体系并评估 OIDC/OAuth2 或服务端 Session，不默认 JWT 或具体库。
  确需解析 JWT 时固定算法并校验 `exp`，按契约校验 `iss`、`aud`、`nbf` 和 Token 类型；
  算法不得由未经约束的 Header 决定。
- 认证密钥只来自受控环境。认证依赖解析身份，授权依赖检查权限、租户和所有权，并在
  写入前完成敏感授权。浏览器 Cookie 使用 `HttpOnly`、`Secure`、合适的 `SameSite`
  和 CSRF 防护；按威胁模型实现速率限制、审计及适用的缺失/无效/过期凭据、越权、
  跨租户和泄漏测试。
- `BackgroundTasks` 只适合允许进程退出时丢失、不要求重试或状态可见性的尽力而为任务。
  需要重试、去重、状态/死信、定时/ETA、优先级/限流、CPU 密集/独立扩缩容，或丢失
  影响承诺、账务、通知、数据完整性时，才选型并添加独立任务系统；依据可靠性语义，
  不按耗时判断。
- 仅在性能数据或外部限制证明必要时引入缓存。先明确键中的身份、租户、版本和查询参数，
  以及 TTL、失效、一致性、穿透/击穿和故障策略；不预建通用 CacheService，也不在缺少
  撤销语义时缓存授权结果。

### 前端与流式响应

- 托管构建后的前端资产时，应用级前端使用 `app.frontend()`，领域前端使用
  `router.frontend()`；保留普通 API 路由的更高匹配优先级，不为 SPA 手工挂载
  `StaticFiles` 和路由回退。
- JSON Lines 端点声明 `AsyncIterable[T]` 返回类型并 `yield` 类型化对象。SSE 端点设置
  `response_class=EventSourceResponse`；普通对象由 Pydantic 序列化，需要控制 `event`、
  `id`、`retry`、`comment` 或发送预格式化字符串时使用 `ServerSentEvent`。
- 字节流端点在装饰器声明 `StreamingResponse` 或其子类并使用 `yield`；同步阻塞的文件
  读取使用同步 `def`，不在异步路径操作中直接构造并返回 `StreamingResponse`。
