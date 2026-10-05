# ATLAS on AWS — Terraform

Initial AWS provisioning baseline: Cognito user pool/app client, encrypted
Multi-AZ RDS PostgreSQL, Secrets Manager database URL, ECS task autoscaling, an
ALB fronting MCP, and a least-purpose Bedrock model permission.

> This Terraform has not been applied to an AWS account or capacity-tested.
> Passing `terraform validate` is not production certification or proof of
> million-user capacity. Validate networking/service discovery, migrations,
> quotas, recovery, security monitoring, and traffic with an AWS deployment
> before storing user data.

## Layout

```
VPC 10.0.0.0/16  (2 public subnets)
├── RDS PostgreSQL 15  (atlas db)          ← schema.sql applied once
├── ECS Fargate x4 on shared cluster:
│   ├── risk        :8000  (PyTorch scorer)
│   ├── finance     :8001  (needs RISK_MODEL_URL)
│   ├── scheduling  :8002  (plain)
│   └── mcp         :8003  (fastmcp, Cognito JWT required)
├── ALB :443 → /mcp* → mcp target group
├── Cognito hosted UI + OAuth authorization-code/PKCE app client
└── IAM: ECS exec + task roles; Bedrock policy scoped to one model
```

## Steps

```bash
export TF_VAR_db_password='<random>'
export TF_VAR_certificate_arn='arn:aws:acm:us-east-1:…'
export TF_VAR_cognito_domain_prefix='<globally-unique-prefix>'
export TF_VAR_cognito_callback_urls='["https://<dashboard>/auth/callback"]'
export TF_VAR_cognito_logout_urls='["https://<dashboard>/"]'

terraform init
terraform plan
terraform apply

# apply the schema once the DB is up:
psql "postgresql://atlas_user:$(echo $TF_VAR_db_password)@<rds-endpoint>/atlas" \
  -f services/common/atlas_common/schema.sql

# push service images to ECR and update image variables
```

## Notes

- Database connection is injected from Secrets Manager; protect Terraform state
  because the database password is an input to the secret resource.
- Only the MCP service is load-balanced in this file; finance/scheduling are
  VPC-internal. This is not yet a complete ingress topology for all dashboard
  REST routes.
- ECS CPU target tracking scales tasks from the configured minimum to maximum.
  It does not prove the database, caches, model service, or ingress can sustain
  that concurrency; establish load targets and test end-to-end before scale
  claims.
- Bedrock policy authorizes **only** the configured foundation model.
- Cognito pool and public app client IDs are available as Terraform outputs.
  Set matching `NEXT_PUBLIC_COGNITO_*` dashboard build variables and exact
  callback URLs.