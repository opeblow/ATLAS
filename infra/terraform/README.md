# ATLAS on AWS — Terraform

Server-side provisioning recipe for the mini-challenge: an RDS Postgres
instance, four Fargate services, an ALB fronting the Streamable HTTP MCP
server, and a Bedrock invocation role. The code is identical to what runs
locally — only `ATLAS_DATABASE_URL` changes.

> Not runnable here: this repo has no Docker and terraform is exercised during
> the AWS build. The goal is a *complete, truthful* recipe, not a partially
> filled config.

## Layout

```
VPC 10.0.0.0/16  (2 public subnets)
├── RDS PostgreSQL 15  (atlas db)          ← schema.sql applied once
├── ECS Fargate x4 on shared cluster:
│   ├── risk        :8000  (PyTorch scorer, no DB env)
│   ├── finance     :8001  (needs RISK_MODEL_URL)
│   ├── scheduling  :8002  (plain)
│   └── mcp         :8003  (fastmcp streamable-http, ATLAS_REQUIRE_AUTH=1)
├── ALB :443 → /mcp* → mcp target group
└── IAM: ECS exec + task roles; Bedrock policy scoped to one model
```

## Steps

```bash
export TF_VAR_db_password='<random>'
export TF_VAR_certificate_arn='arn:aws:acm:us-east-1:…'

terraform init
terraform plan
terraform apply

# apply the schema once the DB is up:
psql "postgresql://atlas_user:$(echo $TF_VAR_db_password)@<rds-endpoint>/atlas" \
  -f services/common/atlas_common/schema.sql

# push your service images to ECR and update the image vars/task definitions
```

## Notes

- `aws_ecs_task_definition` inlines `ATLAS_DATABASE_URL`; for real deployments,
  pull it from SSM instead (the interface in `atlas_common/config.py` already
  reads env).
- Only the MCP service is load-balanced in this file; finance/scheduling are
  VPC-internal (reachable by the orchestrator/dashboard tasks). Add target
  groups + listener rules for them the same way.
- Bedrock policy authorizes **only** the configured foundation model.
- `aws_db_instance` uses `skip_final_snapshot` for a throwaway; remove it in
  production.