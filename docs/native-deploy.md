# 原生服务部署

本项目服务器部署不依赖 Docker。服务器使用 MongoDB 和 Qdrant，并使用 systemd 管理进程。

## 服务端口

- MongoDB: `27017`
- Qdrant HTTP: `6333`
- Qdrant gRPC: `6334`

## 目录

- 项目目录：`/opt/rag-platform`
- 模型目录：`/opt/rag-platform/models`
- 上传文件：`/opt/rag-platform/uploads`
- MongoDB 数据：`/var/lib/mongodb`
- Qdrant 数据：`/var/lib/qdrant`

## 数据重建

服务器不安装模型时，不在服务器生成 embedding。先在本地生成 1024 维向量并导出快照：

```bash
python3 scripts/export_knowledge_snapshot.py --output exports/knowledge_snapshot.jsonl
```

把 `exports/knowledge_snapshot.jsonl` 上传到服务器后导入：

```bash
python3 scripts/import_knowledge_snapshot.py exports/knowledge_snapshot.jsonl --recreate-qdrant --reset-mongo
```

重建后需要确认：

- MongoDB `user_info` 中存在 `admin / 123456` 和 `user / 123456`
- MongoDB `documents` 中存在已解析文档
- Qdrant `documents` collection 的向量维度为 `1024`
- Qdrant `documents` collection 的实体数量大于 0
