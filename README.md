# FastAPI Template

一个面向生产约束、保持最小结构的 FastAPI 项目模板。当前提供应用配置、SQLAlchemy
异步连接、Alembic、CORS、Sentry、健康检查、共享模型与异常以及测试和 CI 基线。

认证、授权、任务队列、缓存和具体业务领域尚未实现，但其后续实现边界保留在
[AGENTS.md](./AGENTS.md) 中。真实需求出现前，模板不会为这些能力预装依赖或创建
空目录。

## 环境要求

- Python 3.11 或更高版本
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL

## 快速开始

以下命令默认在仓库根目录执行。运行迁移前，先创建与 `.env` 中连接地址匹配的
PostgreSQL 用户和数据库；模板不会自动创建数据库。

```shell
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload
```

服务启动后，存活检查位于 `http://127.0.0.1:8000/healthcheck`。该接口只判断应用
进程是否可响应，不访问数据库，因此不能当作数据库 readiness 检查。

常用质量检查：

```shell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
```

本仓库作为模板不提交 `uv.lock`，CI 使用 `uv sync` 重新解析声明的依赖范围，以便及时
发现上游兼容性问题。生成具体业务项目后，应根据交付方式确定锁文件策略；对需要
可复现部署的应用，通常应从 `.gitignore` 移除 `uv.lock`、生成并提交锁文件，然后在
生产环境使用：

```shell
uv lock
uv sync --frozen --no-dev
```

只有明确接受每次部署重新解析依赖时，才在生产环境继续使用无锁的
`uv sync --no-dev`。

## 配置

应用从系统环境变量和当前工作目录的 `.env` 读取配置；因此 README 中的命令都要求
在仓库根目录执行。完整示例及格式见 [`.env.example`](./.env.example)。

| 变量 | 必填 | 说明 |
|---|---|---|
| `DATABASE_ASYNC_URL` | 是 | SQLAlchemy `postgresql+asyncpg` 异步连接地址 |
| `ENVIRONMENT` | 是 | `LOCAL`、`TESTING`、`STAGING` 或 `PRODUCTION` |
| `DATABASE_POOL_SIZE` | 否 | 常驻连接池大小，默认 `16`；另有 SQLAlchemy 默认的 10 个临时溢出连接 |
| `DATABASE_POOL_TTL` | 否 | 正整数；连接最大存活秒数，默认 `1200`；在下次取连接时检查并回收，不是空闲超时 |
| `DATABASE_POOL_PRE_PING` | 否 | 取连接前是否检查可用性，默认 `true` |
| `APP_VERSION` | 否 | OpenAPI 展示的应用版本，默认 `0.1.0` |
| `ROOT_PATH` | 否 | 反向代理剥离的挂载前缀，默认空字符串 |
| `SENTRY_DSN` | 否 | 设置后启用 Sentry，不设置不阻止启动 |
| `CORS_ORIGINS` | 否 | 允许的明确 Origin JSON 数组；仅接受 HTTP(S) 的协议、主机和可选端口 |
| `CORS_ORIGINS_REGEX` | 否 | 只允许在本地或测试环境使用的 Origin 正则 |
| `CORS_HEADERS` | 否 | 允许的请求头 JSON 数组 |
| `CORS_ALLOW_CREDENTIALS` | 否 | 是否允许 Cookie 等浏览器凭据 |

STAGING 保留 OpenAPI 文档用于预发布验证，PRODUCTION 隐藏 `/docs`、`/redoc` 和
`/openapi.json`；若预发布环境对公网开放，应在反向代理层增加访问控制。

配置加载时会规范化 `CORS_ORIGINS` 的大小写、默认端口和尾部 `/`，并拒绝凭据、路径、
查询参数与片段。配置校验错误不展示原始输入值，避免数据库连接地址中的凭据进入日志。

`ROOT_PATH`、API 路由版本和应用发布版本是三件不同的事：

| 需求 | 做法 |
|---|---|
| 代理把 `/gateway/users` 转发为应用内的 `/users` | 设置 `ROOT_PATH=/gateway` |
| API 契约本身是 `/v1/users` | 在领域 `APIRouter` 上设置 `prefix="/v1"` |
| OpenAPI 展示发布版本 | 设置 `APP_VERSION` |

要求统一 UTC 输出的业务时间字段应显式使用 `src.schemas.UTCDateTime`。该类型在请求
边界拒绝没有时区的时间，并在 JSON 中转换为 UTC `Z` 格式；它也可以直接用于
`list[UTCDateTime]`、`dict[str, UTCDateTime]` 等容器。普通 `datetime` 不会被
`CustomModel` 隐式归一化为 UTC，也不会猜测 naive datetime 的时区。

## 数据库与事务

- 路由通过 `DBSession` 取得请求级 `AsyncSession`，依赖只负责创建和关闭 Session。
- 领域 ORM 模型统一继承 `src.models.Base`；`src.database` 只管理 Engine 和 Session。
- 只读 Service 直接执行查询，不需要提交。
- 顶层写 Service 在所有操作成功后显式调用一次 `commit()`；内部 helper 不得提交。
- 写操作在提交前抛出异常时，Session 关闭会回滚未提交事务。
- 需要在提交前取得数据库生成值时使用 `flush()`，不要提前提交。
- 过滤、JOIN、聚合、排序和分页应由领域 SQL 明确表达；普通响应映射和 Pydantic
  序列化留在应用层，不在全局数据库模块包装通用 `fetch_all()` 或 `execute()`。

```python
# router.py
from src.database import DBSession
from src.items import service


async def create_item(payload: ItemCreate, session: DBSession) -> Item:
    return await service.create_item(session, payload)
```

```python
# service.py
from sqlalchemy.ext.asyncio import AsyncSession


async def create_item(session: AsyncSession, payload: ItemCreate) -> Item:
    item = Item(**payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item
```

FastAPI 会在同一请求中缓存并复用该 Session。存在性和所有权依赖只负责查询、校验，
不应写入或提交；每个写路由应调用一个负责完整业务事务的顶层 Service。

## 数据库模型与迁移

### 1. 定义领域模型

在对应领域的 `models.py` 中定义 ORM 模型，并统一继承 `src.models.Base`。不要为每个
领域创建新的 `DeclarativeBase` 或 `MetaData`，也不需要修改 `src.database`。

```python
# src/items/models.py
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class Item(Base):
    __tablename__ = "item"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
```

表名使用单数 `snake_case`；时间列使用 `_at`，日期列使用 `_date`；同一个外键在所有
表中保持相同列名。共享 `Base.metadata` 已配置约束和索引命名约定。

### 2. 让 Alembic 加载模型

新增领域模型后，在 `alembic/env.py` 的导入区显式导入对应模块：

```python
from src.items import models as items_models  # noqa: F401
```

该导入用于执行模型类定义，把表注册到 `Base.metadata`；变量本身不需要使用。
Alembic 不会扫描 `src` 目录，也不会启动 FastAPI，因此必须保留全部现有领域模型的
导入。遗漏导入可能生成空迁移，或把数据库中的现有表误判为待删除表。模板不使用
动态模块扫描，也不要通过导入 `src.main` 间接加载模型。

`alembic/env.py` 已设置 `target_metadata = Base.metadata`，新增领域时无需再次修改该
配置。

### 3. 生成并检查迁移

```shell
uv run alembic revision --autogenerate -m "create item table"
```

`--autogenerate` 只生成迁移草稿。提交前必须检查新 revision 的 `upgrade()` 和
`downgrade()`，确认表名、可空性、外键、索引、数据库默认值和类型变更符合预期。
特别注意列或表重命名可能被识别为删除后重建。不要修改已经执行过的历史迁移；每次
结构变化都生成新的 revision。

### 4. 应用并验证迁移

```shell
uv run alembic upgrade head
uv run alembic check
```

如需验证迁移可逆性，只在可丢弃的开发或测试数据库执行：

```shell
uv run alembic downgrade -1
uv run alembic upgrade head
```

迁移文件必须保持静态、确定且可审查，不得在运行时读取外部 API 来决定结构。每个
revision 都应提供有意义的 `downgrade()`；但结构可回退不代表数据可恢复，删除列、
截断或不可逆数据转换必须在执行前准备备份和恢复方案。

## 后续业务扩展

模板保留下列扩展方向，但它们不是当前能力。开始实现前，先确认对应触发条件，再按
[AGENTS.md](./AGENTS.md) 的条件性规则设计和测试。

| 能力 | 何时引入 | 主要边界 |
|---|---|---|
| 业务领域 | 出现第一个真实业务用例 | 按领域建包，只创建实际需要的模块 |
| 认证与授权 | 出现用户、机器身份或受保护资源 | 先确认身份来源、会话或 Token、撤销与授权模型；不得硬编码密钥 |
| 后台任务 | 请求外工作需要可靠执行、重试、调度或独立扩缩容 | `BackgroundTasks` 只承担允许丢失的尽力而为任务；可靠任务使用独立 Worker |
| 缓存 | 性能数据或外部限额证明缓存有必要 | 先定义缓存键、TTL、失效、一致性和敏感数据隔离 |
| 领域配置 | 配置只属于某一领域并具有独立环境变量前缀 | 再拆分领域 `BaseSettings`，不要预建空配置类 |

## 目录约定

当前共享模块和未来领域的放置方式如下；`{domain}/` 只有在真实业务出现后才创建：

```text
src/
|-- config.py
|-- constants.py
|-- database.py
|-- exceptions.py
|-- main.py
|-- models.py
|-- schemas.py
|-- utils.py
`-- {domain}/
    |-- router.py
    |-- schemas.py
    |-- models.py
    |-- service.py
    |-- dependencies.py
    `-- exceptions.py
```

不要为单一实现提前增加 Repository、BaseService、工厂或插件系统。跨领域引用使用
明确模块名，领域路由统一在 `src.main` 挂载；领域配置、常量或工具文件只在实际需要
时创建。
