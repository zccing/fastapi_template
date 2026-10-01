# AGENTS

## 工作流程

这是基础设施模板，当前没有业务领域、认证、任务队列、缓存或前端。Python 与依赖范围以
`pyproject.toml` 为准；安装、配置、部署和锁文件策略以 [README.md](README.md) 为准。

1. 先检查工作区和相关调用链，保留无关改动；只为当前需求添加模块和依赖。
2. 修复问题时先复现并补回归测试；改变校验时覆盖有效输入和无效输入。
3. 同步更新受影响的配置示例、文档、测试和 CI。引入新能力后，把已经落地的约定写回本文。
4. 在仓库根目录完成检查；报告实际结果、跳过项及未验证的外部行为：

```shell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
```

## 模块与扩展

`src/main.py` 只组装应用、生命周期、中间件和 Router；`src/config.py` 负责配置。
`src/database.py` 管理 Engine、Session 工厂及依赖；`src.models.Base` 是唯一 ORM Base。
当前配置和 Engine 在模块导入时构造，连接在首次使用时建立，退出由 lifespan 释放。
Sentry 在应用入口按配置初始化；导入模型或迁移代码时不要引入应用入口。

第一个领域用例出现后，在 `src/{domain}/` 按需创建 `router.py`、`schemas.py`、
`models.py`、`service.py`、`dependencies.py`、`exceptions.py` 等。不要预建空目录、通用
Repository 或 BaseService。跨领域使用明确模块名；仅应用基础设施或两个以上领域中
语义相同的代码放到共享模块。

**新增认证、后台任务、缓存、前端托管或流式端点时，先读
[按需扩展](docs/extensions.md)**，确认对应契约和依赖；没有需求时不应用这些分支。

## FastAPI 与异步边界

- Router 只处理 HTTP 适配；可复用的存在性、所有权和权限检查放依赖，业务写入放 Service。
  Router 上声明 `prefix`、`tags` 和共享依赖，`include_router()` 只挂载。
- FastAPI 参数使用 `Annotated`；复用依赖定义命名别名。实例由函数依赖返回，保留请求内
  缓存；确需重复执行时才关闭。依赖链使用相同的路径参数名。
- 一个函数处理一个 HTTP 方法。声明返回类型、状态码及适用的错误响应；对外模型与内部
  返回类型不同时才用 `response_model`。让 FastAPI 序列化，请求校验保持默认 422。
- `src.exceptions` 提供安全的客户端消息；领域异常放领域中，底层异常细节只进入内部日志。
  401 表示身份缺失或无效，403 表示身份有效但权限不足。
- 原生异步 I/O 使用 `async def` 和 `await`；只有同步阻塞客户端时优先使用同步路由。
  异步请求中确需同步阻塞调用时，再添加 Asyncer 并只包装最小区段；线程资源有限。
  CPU 密集任务用进程或独立 Worker，依据资源、可靠性和压测决定拆分。
- 新的应用级客户端由 lifespan 创建和关闭，通过应用状态或依赖提供。Alembic/CLI
  可显式管理事件循环；请求路径不自行调用 `asyncio.run()`。
- 响应生成后即可释放的 `yield` 依赖使用 `scope="function"`；必须覆盖响应发送或流式
  传输时才用 `scope="request"`。后台或并发任务各自创建并关闭资源。

## 配置与数据契约

- 使用 Pydantic v2 API 和声明式字段约束；必填字段直接声明类型，类型与默认值一致。
  容器请求体使用普通类型与 `Annotated`，不使用 `RootModel`。
- UTC 字段显式使用 `src.schemas.UTCDateTime`：必须有时区，JSON 输出 UTC `Z`，保留微秒。
  `CustomModel` 不隐式转换普通 datetime；测试应覆盖容器中的时间字段。
- 领域配置只在拥有独立消费者、环境变量前缀和校验边界时拆分，继承
  `CustomBaseSettings`。不要对数据库 DSN 使用会改写路径的 HTTP URL 规范化。
- 环境变量优先于 `.env`，显式空值不回退：`SENTRY_DSN`、`CORS_ORIGINS_REGEX` 空值关闭，
  `ROOT_PATH` 空值清除挂载前缀；数组使用 JSON，空数组是 `[]`。必填和数值字段空值报错。
- 新增 Config 字段时同步补 `.env.example` 和 `tests/conftest.py` 的 `TEST_ENVIRONMENT`；
  保留字段集合检查，避免测试读入本机配置或启用外部集成。
- 保留 CORS 与部署校验：明确 Origin 只含 HTTP(S) 协议、主机和端口；凭据模式禁止
  wildcard；STAGING/PRODUCTION 禁止 wildcard 和 Origin 正则。PRODUCTION 关闭 OpenAPI。
  `ROOT_PATH` 是代理剥离前缀，API 版本放领域 Router。
- 部署密钥来自受控环境或 Secret Manager。隐藏 Settings 错误输入和敏感字段 repr；
  `model_dump()`、`ValidationError.errors()` 仍可能含原始值，不能直接记录。

## 数据库与迁移

- 支持 `postgresql+asyncpg` 与文件型 `sqlite+aiosqlite`；SQLite 拒绝内存库、authority、
  查询和片段，每个应用连接启用外键。文件路径保持原文，相对路径基于工作目录。
- 连接池配置由 `create_database_engine()` 统一应用；调用方负责释放自建 Engine。
  `DATABASE_POOL_TTL` 必须大于零。SQLite 部署与池容量说明见 README。
- 路由使用 `DBSession`；Session 在响应发送前关闭，不跨并发任务共享或传给后台任务。
  关系和延迟字段在 Session 有效期内显式加载，避免序列化触发隐式 I/O。
- 只读 Service 不提交；一个写用例由顶层 Service 管理事务并成功后提交一次，helper
  只做 `flush()`。异常时回滚；Savepoint、多提交点和跨资源一致性先定义失败语义并测试。
- 过滤、JOIN、聚合、排序和分页由数据库完成；展示与 Pydantic 序列化留在应用层。
  使用共享 `DB_NAMING_CONVENTION`、单数 snake_case 表名、`_at` 时间列、`_date` 日期列。
- 模型继承 `Base`，并在 `alembic/env.py` 显式导入；使用已有 Alembic 环境。
  `revision --autogenerate` 后检查 upgrade/downgrade、可空性、外键、索引、默认值和重命名。
  保留迁移文件名中的 revision ID，避免同日同名覆盖。
- 连接数据库前确认环境、主机和数据库，不输出凭据。默认只用可丢弃的本地或测试库；
  共享、STAGING、PRODUCTION 必须取得用户对精确目标的明确授权。
- 修改模型或迁移后，在可丢弃 PostgreSQL 和 SQLite 上运行 `upgrade head`、`alembic check`；
  有回退风险时再验证 downgrade/upgrade。迁移必须确定、可审查，不改已执行的 revision。
  结构迁移安全可行时提供 downgrade；不可逆数据迁移说明范围、前置条件与恢复方案。

## 测试边界

- 使用 `httpx.AsyncClient` 和 `ASGITransport`；涉及启动或退出资源时显式进入 lifespan。
- 外部服务通过 `app.dependency_overrides` 替换；fixture 只恢复自己修改的键。
  不清空整个 overrides，也不 monkeypatch 路由内部逻辑。
- 数据库行为测试复用应用引擎配置，SQLite 用临时文件；PostgreSQL 通过
  `TEST_POSTGRES_URL` 显式提供可丢弃测试库，缺失时跳过对应用例。CI 必须提供该变量。
  PostgreSQL 类型、JSON、锁和并发语义使用真实 PostgreSQL，模拟测试不能称集成测试。
- Ruff、Pyright 和 pytest 检查均由 CI 执行；Review 不重复报告工具已稳定覆盖的格式问题。
