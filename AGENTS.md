# AGENTS

本文件是面向代码 Agent 的仓库执行规范。`README.md` 面向项目使用者，说明当前能力、
启动方式和运维流程；本文件说明 Agent 修改代码时必须遵守的当前约束，以及真实业务
出现后才启用的扩展规则。

## 1. 规则作用域

文档中的规则分为两类：

- **当前规则**：与仓库现有代码、配置和工具直接对应，任何修改都必须遵守。
- **条件性规则**：认证、任务队列、缓存和业务领域等尚未实现的能力；保留这些规则是
  为了指导后续实现，但不得仅因为本文件描述了它们就提前创建目录、安装依赖或搭建
  抽象。

发生冲突时，按以下顺序确认事实：

1. 用户当前明确要求和安全边界。
2. `pyproject.toml` 中的 Python 与依赖约束。
3. 当前代码、测试、Alembic 配置和 CI 行为。
4. `README.md` 中的使用和运维说明。
5. 本文件中的通用实现模式。

不要在本文件复制依赖版本表。最低版本以 `pyproject.toml` 为准，模板是否提交锁文件
以及生成项目如何锁定依赖以 `README.md` 为准。

## 2. 当前项目基线

当前模板已经提供：

- Pydantic Settings 应用配置和部署边界校验。
- SQLAlchemy 异步 Engine、请求级 `AsyncSession` 和 Alembic 异步迁移环境。
- CORS、Sentry、FastAPI lifespan 和不访问数据库的存活检查。
- 共享 ORM Base、Pydantic Base、HTTP 异常和无领域通用工具。
- Ruff、Pyright、pytest 和 GitHub Actions 检查基线。

当前没有业务领域、用户认证、授权模型、任务队列、定时任务或缓存。只有在真实需求
要求这些能力时，才应用第 9 节的条件性规则。

所有命令默认在仓库根目录执行：

```shell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
```

修改前后都要检查 `git status --short` 和相关 `git diff`。不要覆盖或整理无关改动；
没有用户明确要求时，不要提交、推送、重写历史或执行共享环境迁移。

## 3. 目录和领域边界

当前共享模块结构如下：

```text
src/
|-- config.py       # 应用级配置
|-- constants.py    # 环境枚举和数据库命名约定
|-- database.py     # Engine、SessionFactory、DBSession
|-- exceptions.py   # 共享 HTTP 异常
|-- main.py         # FastAPI app、中间件和 lifespan
|-- models.py       # 共享 SQLAlchemy Base
|-- schemas.py      # 共享 Pydantic Base 和时间序列化
`-- utils.py         # 无领域依赖的通用工具
```

出现第一个真实业务领域后，按领域组织，而不是按技术类型建立全局大目录：

```text
src/
`-- {domain}/
    |-- router.py
    |-- schemas.py
    |-- models.py
    |-- service.py
    |-- dependencies.py
    |-- config.py       # 仅当该领域确实拥有独立配置时创建
    |-- constants.py
    |-- exceptions.py
    `-- utils.py
```

规则：

- 只创建当前领域实际需要的文件；不要为了补齐目录树创建空模块。
- 跨领域引用使用明确模块名，例如 `from src.auth import service as auth_service`。
- 不使用星号导入，不通过深层内部路径耦合另一个领域的实现细节。
- 不为单一实现提前创建 Repository、BaseService、工厂、插件系统或接口层。
- 共享代码只有在两个以上真实领域具有相同语义时才上移到 `src/`。

## 4. FastAPI 异步和生命周期

### 路由选择

| 工作类型 | 实现方式 |
|---|---|
| 可 `await` 的非阻塞 I/O | `async def` 并直接 `await` |
| 只有同步客户端的阻塞 I/O | 优先使用同步 `def` 路由 |
| 异步流程中夹杂少量同步阻塞调用 | `async def` + `await run_in_threadpool(...)` |
| 明显消耗 CPU、影响请求延迟或需要独立扩缩容 | 进程池或独立 Worker |

不要用固定的毫秒数决定是否拆 Worker。根据目标并发、延迟预算、任务可靠性、资源
占用和压测结果判断。同步路由、同步依赖、文件处理等会共享 AnyIO 的线程容量限制，
不要把线程池当作无限资源。

禁止在 `async def` 中直接执行 `requests.get()`、`time.sleep()`、同步 ORM、普通阻塞
文件 I/O 或其他长时间阻塞调用。不存在异步替代时，使用同步路由或
`run_in_threadpool()` 包装最小阻塞区段。

### lifespan

应用级客户端、连接池和需要关闭的资源统一由 `FastAPI(lifespan=...)` 管理：

- startup 阶段创建资源，shutdown 阶段释放资源。
- 不同时混用 lifespan 和旧式 `startup`/`shutdown` handler。
- 当前数据库 Engine 是惰性连接，shutdown 通过 `close_database()` 释放连接池。
- 新增外部客户端时，将实例放入明确的应用状态或依赖中，不创建无法关闭的模块级
  临时客户端。

## 5. Pydantic 和配置

### 当前模型约束

- 新代码使用 Pydantic v2 的 `model_dump()`、`model_dump_json()`、
  `field_validator`、`model_validator`、`field_serializer` 和 `PlainSerializer`。
- `.dict()` 和 `json_encoders` 是弃用接口，不是已移除接口；新代码不得继续引入。
- 优先使用 `Field`、`AwareDatetime`、`EmailStr`、URL 类型和枚举等内置约束。
- 字段类型和默认值必须一致。可选整数应写成
  `int | None = Field(default=None, ge=18)`，而不是给 `int` 字段设置 `None` 默认值。

`src.schemas.UTCDateTime` 的现行契约是：

- 要求统一 UTC 输出的字段必须显式使用该类型，不由 `CustomModel` 猜测字段语义。
- 请求边界拒绝没有时区的输入，不猜测 naive datetime 的时区。
- JSON 输出转换为 UTC `Z` 格式且不截断微秒值。
- `list[UTCDateTime]`、`dict[str, UTCDateTime]` 等容器元素遵循相同规则。

### Settings 拆分条件

当前只有应用级 `src.config.Config`，不要为了未来领域提前拆分。某个领域同时满足下列
条件时，可以创建领域级 `BaseSettings`：

- 配置只由该领域消费；
- 具有清晰且独立的环境变量前缀；
- 能在不读取其他领域配置的情况下独立校验。

领域 Settings 仍应使用独立前缀并忽略其他领域变量：

```python
model_config = SettingsConfigDict(
    env_prefix="DOMAIN_",
    env_file=".env",
    extra="ignore",
)
```

密钥只从环境或 Secret Manager 获取，不得写入代码、示例日志或测试快照。

### 当前运行边界

- `ENVIRONMENT` 必须显式设置为 `LOCAL`、`TESTING`、`STAGING` 或 `PRODUCTION`。
- STAGING 和 PRODUCTION 禁止 wildcard Origin 和 Origin 正则；启用凭据时任何环境都
  禁止 wildcard Origin。
- 明确 Origin 只允许 HTTP(S) 的协议、主机和可选端口；禁止凭据、路径、查询参数和
  片段，并在配置边界完成规范化。
- Settings 校验错误必须隐藏原始输入，避免数据库连接地址和其他密钥进入日志。
- LOCAL、TESTING 和 STAGING 保留 OpenAPI；PRODUCTION 通过 `openapi_url=None`
  隐藏 `/docs`、`/redoc` 和 `/openapi.json`。不要再维护第二套环境字符串集合。
- `ROOT_PATH` 只表示反向代理剥离的挂载前缀，不等于 API 版本前缀。

## 6. 依赖、接口和异常

### FastAPI 依赖

- 使用 `Annotated[T, Depends(...)]`，不要为新代码引入默认参数形式的 `Depends`。
- 存在性、所有权、认证和可复用授权检查放在依赖中；业务写入留在 Service。
- FastAPI 默认在单次请求内缓存相同依赖；只有明确需要重复执行时才关闭缓存。
- 复用依赖的路由保持相同路径参数名，例如统一使用 `profile_id`。
- 依赖是 `async def` 还是 `def` 取决于其实际工作是否可等待；不要让同步 I/O 混入
  异步依赖。

### API 契约

新增端点时明确记录：

- `status_code`、`summary`、`description` 和 `tags`；
- 成功响应模型及业务错误响应；
- 身份、权限、幂等性、分页和限流要求；
- 对外可见的错误码和安全消息。

FastAPI 请求校验默认返回 422。只有项目显式增加统一异常映射后，文档才能把校验
错误写成 400。

返回类型和 `response_model` 相同并不是错误。二者相同时可以只保留返回类型以减少
重复；需要独立的 OpenAPI 契约、输出字段过滤或与内部返回类型解耦时，显式设置
`response_model`。不要以“避免二次构造”为理由删除响应验证。

### 异常边界

- 使用 `src.exceptions` 中的安全客户端消息，领域异常放在领域模块。
- 只捕获能够处理的具体异常；记录内部细节，但不把堆栈、SQL、Token 或密钥返回给
  客户端。
- 捕获 `Exception` 本身不会自动把 500 变成 200；真正的问题是宽泛捕获后错误映射、
  吞掉缺陷或丢失原始异常链。
- 401 表示缺少或无效身份凭据，403 表示身份已确认但权限不足。

## 7. 数据库和事务

当前数据库约束：

- 连接字段是 `DATABASE_ASYNC_URL`，只接受 `postgresql+asyncpg`。
- `DATABASE_POOL_TTL` 必须是正整数；`0` 会导致连接在每次取出时被回收，不能表示禁用。
- 路由通过 `DBSession` 获取请求级 `AsyncSession`。
- `src.database` 只管理 Engine、SessionFactory、依赖和关闭逻辑。
- 所有 ORM 模型继承 `src.models.Base`，不要创建第二套 `DeclarativeBase` 或
  `MetaData`。

事务规则：

- 只读 Service 直接查询，不提交。
- 一个写请求由一个顶层 Service 负责完整事务，并在全部操作成功后提交一次。
- 内部 helper 不提交；需要数据库生成值时使用 `flush()`。
- 提交前抛出异常时允许 Session 关闭并回滚未提交事务。
- 需要多个独立提交点、Savepoint 或跨资源一致性时，先明确失败语义并补充测试，不要
  隐式改变现有事务边界。

过滤、JOIN、聚合、排序和分页应由数据库完成。响应展示格式和普通 Pydantic
序列化通常留在应用层；只有数据库原生 JSON 能明确降低数据传输或复杂度并有测试
支撑时，才在 SQL 中塑造 JSON。

数据库命名沿用 `DB_NAMING_CONVENTION`：单数 `snake_case` 表名，时间列使用 `_at`，
日期列使用 `_date`，同一外键在不同表中保持相同列名。

## 8. Alembic 迁移

仓库已经使用 `alembic/` 作为异步迁移目录，禁止再次运行 `alembic init` 创建第二套
环境。具体操作流程见 README 的“数据库模型与迁移”。

新增或修改模型时：

1. 模型继承共享 `Base`。
2. 在 `alembic/env.py` 显式导入每个领域的 `models` 模块。
3. 运行 `uv run alembic revision --autogenerate -m "..."`。
4. 人工检查 upgrade、downgrade、可空性、外键、索引、默认值和重命名操作。
5. 在可丢弃数据库运行 upgrade、`alembic check`，必要时验证 downgrade 后再 upgrade。

迁移必须静态、确定且可审查；不得在运行时访问外部 API 来决定结构。不要修改已经
执行过的历史 revision。每个 revision 都应提供有意义的 downgrade，但结构可回退
不等于数据可恢复：删除列、截断或不可逆数据转换必须在执行前制定备份和恢复方案。

## 9. 条件性业务扩展

本节保留未来实现规则，但不代表功能当前存在。

### 9.1 认证和授权

触发条件：真实业务需要用户身份、机器身份、会话或受保护资源。认证属于高风险边界，
实现前必须先确认身份来源、Token/Session 传输方式、有效期、撤销策略、授权模型和
客户端类型。

规则：

- 不默认假定 JWT 是唯一方案；优先评估现有 OIDC/OAuth2 身份提供方和服务端 Session。
- 如果确定由本项目解析 JWT，本模板约定使用 PyJWT；届时再添加依赖，不提前安装。
- 解码时固定允许的算法，并校验 `exp`；业务需要时同时校验 `iss`、`aud`、`nbf` 和
  Token 类型。算法不能由未经约束的 Token Header 决定。
- 签名密钥、刷新令牌密钥和客户端 Secret 只来自受控环境，不进入仓库和日志。
- 认证依赖负责解析身份；授权依赖负责角色、权限、租户和资源所有权。敏感写操作在
  Service 执行前完成授权。
- 浏览器使用 Cookie 保存会话或 Token 时，配置 `HttpOnly`、`Secure`、合适的
  `SameSite`，并为状态变更请求设计 CSRF 防护。
- 登录、刷新、重置密码和高成本接口根据威胁模型增加速率限制和审计事件。
- 测试至少覆盖缺少凭据、无效凭据、过期凭据、权限不足、跨租户访问和敏感信息不
  泄漏。

### 9.2 后台任务和调度

`BackgroundTasks` 只适用于同一 Worker 内执行、允许随进程退出丢失、不需要重试或
可见性的尽力而为任务。是否适用由可靠性语义决定，不以“一秒以内”作为硬边界。

以下任一条件成立时使用独立任务系统：

- 必须重试、去重、查看状态或进入死信队列；
- 需要定时、ETA、优先级、速率限制或独立扩缩容；
- CPU 密集，或耗时足以显著占用 Web Worker；
- 任务丢失会影响用户承诺、账务、通知或数据完整性。

Celery、Arq、RQ 等只是候选方案；根据 Broker、调度、运维和可靠性要求选型后再添加
依赖。邮件是否能用 `BackgroundTasks` 取决于是否允许丢失，不能仅因为发送动作看似
简单就默认使用。

### 9.3 缓存

只有性能数据或外部服务限制证明缓存必要时才引入。实现前必须明确：

- 缓存键包含哪些身份、租户、版本和查询参数；
- TTL、主动失效和写后读一致性；
- 缓存穿透、击穿和敏感数据隔离；
- 缓存不可用时是回源、降级还是失败。

不要提前创建通用 CacheService，也不要缓存认证授权结果而没有明确的撤销和失效
语义。

## 10. 测试

### HTTP 测试

异步 API 测试使用 `httpx.AsyncClient` 和 `ASGITransport`。`ASGITransport` 不会自动
执行 ASGI lifespan：测试仅访问不依赖启动资源的端点时可以直接使用；涉及 startup
或 shutdown 资源时，必须显式进入应用 lifespan，或在确有需要时引入专用 lifespan
测试工具。

```python
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client
```

`tests/conftest.py` 必须为 `src.config.Config` 的每个字段提供明确测试值，并禁用 Sentry
等外部集成。新增配置字段时应同步更新隔离值；测试启动检查会阻止遗漏字段进入测试。

### 依赖覆盖

使用 `app.dependency_overrides` 替换认证或外部服务依赖，不直接 monkeypatch 路由内部
实现。Fixture 只恢复自己修改的键；不要调用 `dependency_overrides.clear()` 清除其他
Fixture 的覆盖。

### 数据库测试

- 纯事务生命周期、无 PostgreSQL 特性的单元测试可以使用 SQLite。
- 查询语义、约束、JSON、锁、并发、迁移和 PostgreSQL 特性必须使用真实 PostgreSQL
  测试环境。
- 集成测试如果模拟数据库，就不再验证真实数据库集成；不要把这类测试称为数据库
  集成测试。
- 行为变更优先先写能复现失败的最小测试，再实现修复。

## 11. 质量检查和反模式

默认先运行只读检查；需要自动修复时，只处理本次改动涉及的文件并复核 diff。

| 反模式 | 正确方向 |
|---|---|
| `async def` 中调用同步网络、文件或 ORM API | 异步客户端、同步路由或 `run_in_threadpool` |
| 新代码使用 `.dict()`、`json_encoders` | Pydantic v2 序列化 API |
| 新代码使用默认参数形式 `Depends` | `Annotated[T, Depends(...)]` |
| 宽泛捕获 `Exception` 后返回统一成功或业务错误 | 捕获具体异常，保留异常链和真实状态 |
| 用 `BackgroundTasks` 承担可靠任务 | 独立任务系统 |
| 为一个实现创建 Repository、BaseService 或工厂 | 直接实现，出现真实重复后再抽象 |
| 忘记在 Alembic 导入领域模型 | 显式导入并检查 autogenerate diff |
| 把 FastAPI 默认校验错误写成 400 | 默认记录 422，或先实现统一映射 |
| `dependency_overrides.clear()` | 只恢复当前 Fixture 修改的键 |
| 为了“避免二次构造”删除响应验证 | 根据 API 契约选择返回类型或 `response_model` |

## 12. 交付要求

- 每个改动都应能追溯到当前任务；不顺手重构相邻代码。
- 行为、配置、依赖、部署或外部接口变化时，同步更新 README 和对应测试。
- 修改后检查相关 diff，确认没有密钥、Token、数据库转储或本地 `.env`。
- 运行最相关、最低成本的测试和静态检查；无法运行时明确写出 `Unverified` 和原因。
- 最终报告必须说明修改内容、实际执行的验证、未完成项和阻塞项。
