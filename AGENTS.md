# AGENTS

## 当前基线与模板演进

Python 和依赖约束以 `pyproject.toml` 为准，使用与锁文件策略以 `README.md` 为准。
当前模板提供 Pydantic Settings 配置与部署校验、异步 PostgreSQL 和文件型 SQLite、
SQLAlchemy 异步 Engine 与路径操作级 `AsyncSession`、Alembic 异步迁移、CORS、Sentry、
FastAPI lifespan、不访问数据库的存活检查、共享 ORM/Pydantic Base、HTTP 异常、无领域
工具，以及 Ruff、Pyright、pytest 和 CI。

当前没有业务领域、认证授权、任务队列、定时任务或缓存；只有真实需求触发时才应用
“条件性扩展”。所有命令默认在仓库根目录执行：

```shell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
```

通过模板生成的业务项目应完成 README 的定制项并跟踪自己的依赖锁文件。能力落地时，
将对应条件性规则改为当前规则，写明实际模块、依赖和验证方式，删除“当前没有该能力”
等失效描述，并保持代码、配置、测试、CI、README 与本文一致。

## 目录与领域边界

当前 `src/` 只放应用级配置、数据库、异常、生命周期、共享 Base 和无领域工具。以下
目录树表示领域代码允许的放置位置，不是必建清单；只创建当前用例实际需要的文件：

```text
src/
`-- {domain}/
    |-- router.py
    |-- schemas.py
    |-- models.py
    |-- service.py
    |-- dependencies.py
    |-- config.py       # 仅当该领域拥有独立配置时
    |-- constants.py
    |-- exceptions.py
    `-- utils.py
```

跨领域引用使用明确模块名，不用星号导入或另一领域的深层内部实现。代码默认留在领域
内，只有两个以上领域语义相同，或能力本身属于应用级基础设施时，才上移到 `src/`。

## FastAPI、Pydantic 与配置

### 异步与生命周期

| 工作类型 | 实现方式 |
|---|---|
| 可 `await` 的非阻塞 I/O | `async def` 并直接 `await` |
| 只有同步客户端的阻塞 I/O | 优先使用同步 `def` 路由 |
| 异步流程中的少量同步阻塞调用 | 确认无异步替代后，按需添加 Asyncer 并只包装最小区段 |
| CPU 密集或需要独立扩缩容 | 进程池或独立 Worker |

- 禁止在 `async def` 中直接执行同步网络、同步 ORM、`time.sleep()`、普通阻塞文件 I/O
  或其他长时间阻塞调用；没有异步替代时，使用同步路由或只包装最小阻塞区段。
- 当前模板不额外安装专用同步/异步桥接库。业务请求路径确需从异步代码调用同步阻塞函数时，
  再添加 Asyncer 并使用 `asyncify()`；不直接混用 AnyIO、asyncio 或 Starlette 的线程桥接
  API。Alembic、CLI 等独立入口可显式管理事件循环，现有迁移入口保留 `asyncio.run()`。
- 不用固定耗时决定是否拆 Worker；依据并发、延迟、可靠性、资源和压测。同步路由、
  同步依赖、文件处理和线程桥接最终仍消耗线程资源，不能视为无限容量。
- 应用级客户端、连接池和需关闭资源由 `FastAPI(lifespan=...)` 创建、释放，不与旧式
  `startup`/`shutdown` handler 混用。当前 Engine 惰性连接，shutdown 通过
  `close_database()` 释放；新增客户端放入明确的应用状态或依赖，不创建无法关闭的
  模块级临时客户端。

### Pydantic 与 Settings

- 新代码使用 Pydantic v2 的 `model_dump()`/`model_dump_json()`、`field_validator`/
  `model_validator`、`field_serializer`/`PlainSerializer`，不引入 `.dict()` 或
  `json_encoders`。优先使用 `Field`、`AwareDatetime`、URL 类型和枚举；`EmailStr` 等
  依赖可选包的类型需先确认需求并添加依赖。
- 类型和默认值必须一致，例如 `int | None = Field(default=None, ge=18)`；必填字段直接
  声明类型，不用 `field: T = ...` 或 `Field(...)`。
- 不创建 Pydantic `RootModel`；容器或标量请求体使用普通类型、`Annotated` 和 Pydantic
  约束。
- 统一 UTC 输出的字段显式使用 `src.schemas.UTCDateTime`，不由 `CustomModel` 猜测。
  该类型拒绝无时区输入，输出 UTC `Z` 且不截断微秒，容器元素规则相同。
- 当前只有应用级 `src.config.Config`。领域配置仅在单一领域消费、拥有独立环境变量前缀
  且可独立校验时拆分；继承 `src.config.CustomBaseSettings`，设置独立 `env_prefix`、
  `env_file=".env"`、`extra="ignore"` 和 `hide_input_in_errors=True`。
- 本地开发可使用 Git 忽略的 `.env`；STAGING 和 PRODUCTION 的密钥由受控环境变量或
  Secret Manager 注入。密钥不进入代码、示例、日志或测试快照；Settings 错误隐藏原始
  输入，避免连接地址和密钥进入日志。
- `ENVIRONMENT` 必须显式为 `LOCAL`、`TESTING`、`STAGING` 或 `PRODUCTION`。STAGING 与
  PRODUCTION 禁止 wildcard Origin 和 Origin 正则；启用凭据时任何环境都禁止 wildcard
  Origin。明确 Origin 只允许 HTTP(S) 协议、主机和可选端口，禁止凭据、路径、查询和
  片段，并在配置边界规范化。
- LOCAL、TESTING、STAGING 保留 OpenAPI；PRODUCTION 通过 `openapi_url=None` 隐藏
  `/docs`、`/redoc`、`/openapi.json`，不维护第二套环境字符串集合。`ROOT_PATH` 只表示
  反向代理剥离的挂载前缀，不是 API 版本前缀。

## API、数据库与迁移

### 依赖、契约与异常

- FastAPI 参数声明统一使用 `Annotated`，包括 `Path`、`Query`、`Header`、`Body` 和
  `Depends`；复用依赖定义为命名类型别名。避免直接使用类依赖，需要实例时由函数依赖
  返回。
- 存在性、所有权、认证和可复用授权检查放在依赖中，业务写入留在 Service；复用依赖
  的路由保持相同路径参数名，依赖用 `async def` 还是 `def` 取决于工作是否可等待。
- 相同依赖默认使用请求内缓存，只有确需重复执行时才关闭。响应生成后可释放的 `yield`
  依赖用 `scope="function"`；必须覆盖响应发送或流式传输时才用 `scope="request"`。
- 领域 Router 的 `prefix`、`tags` 和共享依赖定义在 `APIRouter` 上，`include_router()`
  只负责挂载；一个路径操作函数只处理一个 HTTP 方法。
- 新端点明确 `status_code`、OpenAPI 摘要、说明与标签、成功响应、业务错误和安全错误码；
  只记录实际适用的身份、权限、幂等性、分页和限流要求。
- 请求校验默认返回 422，只有已实现统一映射时才能记录为 400。常规端点显式声明返回
  类型，由 FastAPI 完成验证、过滤、序列化和 OpenAPI 生成；只有对外模型与内部返回
  类型不同时才设置 `response_model`，不重复声明相同类型。不要使用已弃用的
  `ORJSONResponse` 或 `UJSONResponse`。
- 复用 `src.exceptions` 的安全客户端消息，领域异常放在领域模块；401 表示缺少或无效
  身份，403 表示身份有效但权限不足。

### 数据库、事务与 Alembic

- `DATABASE_ASYNC_URL` 只接受 `postgresql+asyncpg` 或文件型 `sqlite+aiosqlite`。SQLite
  不接受 `:memory:`、authority、查询或片段；每个应用连接启用外键约束。部署 SQLite 时
  使用持久化可写卷并优先保持单实例、低写并发；需要多副本或高写并发时使用 PostgreSQL。
- `DATABASE_POOL_TTL` 必须为正整数，`0` 会使连接每次取出时回收，不能表示禁用。
- 路由通过 `DBSession` 获取路径操作级 `AsyncSession`，响应发送前关闭；`src.database`
  只管理 Engine、SessionFactory、依赖和关闭；ORM 模型均继承 `src.models.Base`，不创建
  第二套 `DeclarativeBase` 或 `MetaData`。
- `AsyncSession` 只属于一个请求或独立任务及其事务；不在并发任务间共享，也不传入
  `BackgroundTasks` 或独立 Worker。每个并发任务或后台任务自行创建和关闭 Session。
- 异步 ORM 响应映射不依赖关系或延迟字段的隐式 I/O；序列化所需数据在 Session 有效期内
  显式加载完成。
- 只读 Service 不提交。一个写请求由一个顶层 Service 管理事务并成功后提交一次；helper
  不提交，需要数据库生成值时 `flush()`，异常时回滚。多提交点、Savepoint 或跨资源
  一致性须先定义失败语义并补测试，不隐式改变事务边界。
- 过滤、JOIN、聚合、排序和分页由数据库完成；展示和普通 Pydantic 序列化留在应用层，
  仅在有明确收益和测试时由 SQL 塑造 JSON。
- 沿用 `DB_NAMING_CONVENTION`：单数 `snake_case` 表名，时间列 `_at`，日期列 `_date`，
  相同外键保持相同列名。

仓库已有异步 `alembic/`，不得再次运行 `alembic init`。运行任何连接数据库的 Alembic
命令前，先确认目标环境、主机和数据库且不输出凭据。默认只连接可丢弃的本地或测试
数据库；连接共享、STAGING 或 PRODUCTION 数据库必须先取得用户对精确目标的明确授权。
新增或修改模型时：

1. 继承共享 `Base`，并在 `alembic/env.py` 显式导入领域 `models`。
2. 运行 `uv run alembic revision --autogenerate -m "..."`。
3. 人工检查 upgrade、downgrade、可空性、外键、索引、默认值和重命名。
4. 在可丢弃 PostgreSQL 和 SQLite 验证 upgrade、`alembic check`；风险需要时再验证
   downgrade 后 upgrade。

迁移必须静态、确定、可审查，不访问外部 API 决定结构，也不修改已执行的 revision。
结构迁移在安全可行时提供有意义的 downgrade；不可逆数据迁移不得伪造可恢复性，必须
说明不可逆范围、前置条件、备份与恢复方案。

## 条件性扩展

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

## 测试与质量检查

- 异步 API 测试使用 `httpx.AsyncClient` 和 `ASGITransport`；后者不自动执行 lifespan，
  涉及 startup 或 shutdown 资源时显式进入应用 lifespan。
- `tests/conftest.py` 为 `src.config.Config` 每个字段提供明确测试值，并禁用 Sentry 等
  外部集成；新增字段时同步更新隔离值，保留启动检查以阻止遗漏。
- 用 `app.dependency_overrides` 替换认证或外部服务依赖。Fixture 只恢复自己修改的键，
  不调用 `dependency_overrides.clear()`，也不直接 monkeypatch 路由内部实现。
- 后端无关的模型、查询和迁移行为在 PostgreSQL 与文件型 SQLite 上验证；PostgreSQL
  专属类型、JSON、锁和并发语义使用真实 PostgreSQL。模拟数据库的测试不称数据库集成
  测试。
- Ruff、格式化和 Pyright 已由项目 CI 覆盖；Review 通常不重复报告这些工具能稳定发现的
  问题，除非 CI 未覆盖或它掩盖了实际缺陷。
