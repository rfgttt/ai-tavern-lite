# AI Tavern Lite 数据库迁移

项目使用 Alembic 管理数据库结构版本。应用启动时会自动执行以下流程：

1. 对现有 SQLite 数据库创建一致性备份；
2. 将数据库升级到最新 Alembic `head`；
3. 校验当前版本、表、字段和关键索引；
4. 迁移或校验失败时停止启动；
5. SQLite 迁移失败时自动恢复启动前备份。

## 当前基线

```text
Revision: 20260717_0001
用途: 建立当前 2.2 Preview 数据库基线，并接管旧的无版本数据库
```

首次应用时：

- 空数据库会创建完整表结构；
- 当前已有数据库不会删除或重建用户表；
- 旧数据库会补齐已知安全字段；
- 重复的消息序号会按原顺序重新编号；
- 数据库会增加 Alembic 自己使用的 `alembic_version` 表。

## 常用命令

在项目根目录运行：

```powershell
.\scripts\database-migrate.ps1 status
.\scripts\database-migrate.ps1 validate
.\scripts\database-migrate.ps1 history
.\scripts\database-migrate.ps1 heads
```

手动执行带备份的升级：

```powershell
.\scripts\database-migrate.ps1 upgrade
```

通常不需要手动执行 `upgrade`，因为 `start.ps1` 启动应用时会自动迁移。

## 创建后续迁移

先修改 SQLAlchemy 模型，再进入后端目录生成迁移草稿：

```powershell
Set-Location ".\backend"
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "describe schema change"
```

生成后必须人工检查迁移脚本，特别是 SQLite 的表重建、字段默认值、数据回填和索引变化。自动生成结果不能未经检查直接应用。

验证迁移：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_migrations.py -q
Set-Location ".."
.\verify-release.ps1 -SkipNpmCi
```

## 安全规则

- 不要手工修改 `alembic_version`；
- 不要删除已经提交并发布的迁移文件；
- 每次数据库结构变更使用独立迁移；
- 迁移中涉及删除或改名时，先做数据复制和验证；
- 不运行 `alembic downgrade base`：初始基线明确阻止该操作，因为它会删除全部用户数据；
- 需要回退数据库时，使用 `backend/data/backups` 中的备份。
