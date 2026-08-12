The platform image is built from the repository root.

```bash
docker compose -f ../docker-compose.yml up --build
```

`Dockerfile` at the repo root is the source of truth so sample targets stay bind-mounted at `/app/samples`.
