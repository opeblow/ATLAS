variable "region" {
  default = "us-east-1"
}

variable "db_instance_class" {
  default = "db.t4g.micro"
}

variable "db_user" {
  default = "atlas_user"
}

variable "db_password" {
  description = "RDS master password (set via terraform.tfvars / TF_VAR_db_password, never commit)"
  sensitive   = true
}

variable "certificate_arn" {
  description = "ACM certificate ARN for the ALB HTTPS listener"
  type        = string
  default     = ""
}

variable "bedrock_model" {
  default = "amazon.nova-micro-v1:0"
}

variable "cognito_domain_prefix" {
  description = "Globally unique Cognito hosted UI domain prefix."
  type        = string
}

variable "cognito_callback_urls" {
  description = "Exact OAuth callback URLs; include the dashboard's /auth/callback."
  type        = list(string)
  default     = ["http://localhost:3000/auth/callback"]
}

variable "cognito_logout_urls" {
  description = "Allowed post-logout URLs."
  type        = list(string)
  default     = ["http://localhost:3000/"]
}

variable "ecs_min_capacity" {
  description = "Minimum tasks per ECS service across availability zones."
  type        = number
  default     = 2
}

variable "ecs_max_capacity" {
  description = "Maximum tasks per ECS service under CPU target tracking."
  type        = number
  default     = 40
}

variable "risk_image" { default = "000000000000.dkr.ecr.us-east-1.amazonaws.com/atlas/risk-model" }
variable "finance_image" { default = "000000000000.dkr.ecr.us-east-1.amazonaws.com/atlas/finance-service" }
variable "scheduling_image" { default = "000000000000.dkr.ecr.us-east-1.amazonaws.com/atlas/scheduling-service" }
variable "mcp_image" { default = "000000000000.dkr.ecr.us-east-1.amazonaws.com/atlas/mcp-server" }