# FastAPI Template

一个保持最小结构、面向生产部署的 FastAPI 项目模板。当前只提供应用配置、
SQLAlchemy 异步连接、Alembic、CORS、Sentry 接入、健康检查和测试基线；认证、
任务队列、缓存和业务领域应在真实需求出现后再加入。

## 环境要求

- Python 3.11 或更高版本
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL，以及与服务端兼容的 PostgreSQL 客户端工具

## 快速开始

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
sh -n scripts/postgres/backup scripts/postgres/restore
```

本仓库作为项目模板，不提交 `uv.lock`。使用方可以在生成具体项目后，按自己的交付
策略决定是否提交锁文件。

生产环境只安装运行依赖时使用：

```shell
uv sync --no-dev
```

## 配置

应用从系统环境变量和项目根目录的 `.env` 读取配置。完整示例及格式见
[`.env.example`](./.env.example)。

| 变量 | 必填 | 说明 |
|---|---|---|
| `DATABASE_ASYNC_URL` | 是 | SQLAlchemy `postgresql+asyncpg` 异步连接地址 |
| `ENVIRONMENT` | 是 | `LOCAL`、`TESTING`、`STAGING` 或 `PRODUCTION` |
| `DATABASE_POOL_SIZE` | 否 | 常驻连接池大小，默认 `16`；另有 SQLAlchemy 默认的 10 个临时溢出连接 |
| `DATABASE_POOL_TTL` | 否 | 连接回收秒数，默认 `1200` |
| `DATABASE_POOL_PRE_PING` | 否 | 取连接前是否检查可用性，默认 `true` |
| `APP_VERSION` | 否 | OpenAPI 展示的应用版本，默认 `0.1.0` |
| `ROOT_PATH` | 否 | 反向代理剥离的挂载前缀，默认空字符串 |
| `SENTRY_DSN` | 否 | 设置后启用 Sentry，不设置不阻止启动 |
| `CORS_ORIGINS` | 否 | 允许的明确 Origin JSON 数组 |
| `CORS_ORIGINS_REGEX` | 否 | 只允许在本地或测试环境使用的 Origin 正则 |
| `CORS_HEADERS` | 否 | 允许的请求头 JSON 数组 |
| `CORS_ALLOW_CREDENTIALS` | 否 | 是否允许 Cookie 等浏览器凭据 |

STAGING 保留 OpenAPI 文档用于预发布验证，PRODUCTION 隐藏 `/docs`、`/redoc` 和
`/openapi.json`；若预发布环境对公网开放，应在反向代理层增加访问控制。

`ROOT_PATH`、API 路由版本和应用发布版本是三件不同的事：

| 需求 | 做法 |
|---|---|
| 代理把 `/gateway/users` 转发为应用内的 `/users` | 设置 `ROOT_PATH=/gateway` |
| API 契约本身是 `/v1/users` | 在领域 `APIRouter` 上设置 `prefix="/v1"` |
| OpenAPI 展示发布版本 | 设置 `APP_VERSION` |

业务模型中的时间字段应使用 Pydantic `AwareDatetime`，在请求边界拒绝没有时区的
时间。`CustomModel` 将带时区时间转换为 UTC `Z` 格式并保留微秒精度，不会猜测
naive datetime 属于哪个时区。

## 数据库与事务

- 路由通过 `DBSession` 取得请求级 `AsyncSession`，依赖只负责创建和关闭 Session。
- 领域 ORM 模型统一继承 `src.models.Base`；`src.database` 只管理 Engine 和 Session。
- 只读 Service 直接执行查询，不需要提交。
- 顶层写 Service 在所有操作成功后显式调用一次 `commit()`；内部 helper 不得提交。
- 写操作在提交前抛出异常时，Session 关闭会回滚未提交事务。
- 需要在提交前取得数据库生成值时使用 `flush()`，不要提前提交。
- JOIN、聚合、分页和返回结构应由领域 SQL 明确表达，不在全局数据库模块包装通用
  `fetch_all()` 或 `execute()`。

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

迁移文件必须保持静态、可逆，不得在运行时读取外部 API 或当前业务数据来决定结构。

## PostgreSQL 备份与恢复

脚本读取 libpq 支持的连接环境变量。至少需要设置 `POSTGRES_USER` 和
`POSTGRES_DB`；主机、端口和凭据应由部署平台、secret manager 或 `.pgpass` 提供，
不要写入仓库。

```shell
POSTGRES_USER=app POSTGRES_DB=app scripts/postgres/backup
```

备份默认写入 `/backups`，可以用 `BACKUP_DIRECTORY` 覆盖。脚本使用 PostgreSQL
custom archive 格式，并在报告成功前调用 `pg_restore --list` 验证归档。

恢复会删除并重建目标数据库，必须显式传入确认参数：

```shell
POSTGRES_USER=app POSTGRES_DB=app \
  scripts/postgres/restore backup-2026-07-19-120000Z.a1B2c3.dump --confirm-drop
```

备份文件名包含 UTC 时间和随机后缀，避免同一秒内并发或重试相互覆盖。恢复脚本只
接受备份目录内的普通文件名，并在删除数据库前验证归档；同时兼容旧的 `.dump.gz`
文件。即便如此，生产恢复仍应先在隔离数据库演练并验证数据。

## 目录约定

当前没有虚构业务领域。加入第一个真实领域时，按领域组织代码：

```text
src/
|-- example/
|   |-- router.py
|   |-- schemas.py
|   |-- models.py
|   |-- service.py
|   |-- dependencies.py
|   `-- exceptions.py
|-- config.py
|-- database.py
|-- models.py
`-- main.py
```

不要为单一实现提前增加 Repository、BaseService、工厂或插件系统。跨领域引用使用
明确模块名，领域路由统一在 `src.main` 挂载。
