terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {
    # bucket = "atlas-terraform-state"
    # key    = "atlas/terraform.tfstate"
    # region = "us-east-1"
  }
}

provider "aws" {
  region = var.region
}

locals {
  name = "atlas"
  auth_environment = [
    { name = "ATLAS_AUTH_MODE", value = "cognito" },
    { name = "ATLAS_REQUIRE_AUTH", value = "1" },
    { name = "ATLAS_COGNITO_USER_POOL_ID", value = aws_cognito_user_pool.atlas.id },
    { name = "ATLAS_COGNITO_APP_CLIENT_ID", value = aws_cognito_user_pool_client.atlas.id },
    { name = "AWS_REGION", value = var.region },
    { name = "ATLAS_DB_POOL_SIZE", value = "3" },
    { name = "ATLAS_DB_MAX_OVERFLOW", value = "2" },
  ]
  common_tags = {
    Project   = "ATLAS"
    Service   = "Agentic Chief of Staff"
    ManagedBy = "terraform"
  }
}

# ------------------------------------------------------------------ network
resource "aws_vpc" "atlas" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = local.common_tags
}

resource "aws_subnet" "atlas" {
  count                   = 2
  vpc_id                  = aws_vpc.atlas.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = "${var.region}${count.index == 0 ? "a" : "b"}"
  map_public_ip_on_launch = true
  tags                    = local.common_tags
}

resource "aws_internet_gateway" "atlas" {
  vpc_id = aws_vpc.atlas.id
  tags   = local.common_tags
}

resource "aws_route_table" "atlas" {
  vpc_id = aws_vpc.atlas.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.atlas.id
  }
  tags = local.common_tags
}

resource "aws_route_table_association" "atlas" {
  count          = 2
  subnet_id      = aws_subnet.atlas[count.index].id
  route_table_id = aws_route_table.atlas.id
}

resource "aws_security_group" "services" {
  name   = "${local.name}-services"
  vpc_id = aws_vpc.atlas.id
  ingress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.common_tags
}

resource "aws_security_group" "lb" {
  name   = "${local.name}-lb"
  vpc_id = aws_vpc.atlas.id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.common_tags
}

# ------------------------------------------------------------------ database
# DDL comes from services/common/atlas_common/schema.sql — apply once via psql.
resource "aws_db_instance" "atlas" {
  identifier             = "${local.name}-db"
  engine                 = "postgres"
  engine_version         = "15.7"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  db_name                = "atlas"
  username               = var.db_user
  password               = var.db_password
  multi_az               = true
  storage_encrypted      = true
  backup_retention_period = 7
  deletion_protection    = true
  vpc_security_group_ids = [aws_security_group.services.id]
  db_subnet_group_name   = aws_db_subnet_group.atlas.name
  skip_final_snapshot    = true
  tags                   = local.common_tags
}

resource "aws_db_subnet_group" "atlas" {
  name       = "${local.name}-subnets"
  subnet_ids = aws_subnet.atlas[*].id
  tags       = local.common_tags
}

resource "aws_secretsmanager_secret" "database_url" {
  name                    = "${local.name}/database-url"
  recovery_window_in_days = 7
  tags                    = local.common_tags
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql+psycopg2://${var.db_user}:${var.db_password}@${aws_db_instance.atlas.endpoint}/atlas"
}

# ------------------------------------------------------------------ identity
resource "aws_cognito_user_pool" "atlas" {
  name                = "${local.name}-users"
  username_attributes = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 1
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = local.common_tags
}

resource "aws_cognito_user_pool_client" "atlas" {
  name                                 = "${local.name}-dashboard"
  user_pool_id                         = aws_cognito_user_pool.atlas.id
  generate_secret                      = false
  prevent_user_existence_errors        = "ENABLED"
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = var.cognito_callback_urls
  logout_urls                          = var.cognito_logout_urls
  access_token_validity                = 60
  id_token_validity                    = 60
  refresh_token_validity               = 7
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

resource "aws_cognito_user_pool_domain" "atlas" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.atlas.id
}

# ------------------------------------------------------------------ cluster
resource "aws_ecs_cluster" "atlas" {
  name = "${local.name}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = local.common_tags
}

locals {
  task_defs = {
    risk       = { image = var.risk_image, port = 8000 }
    finance    = { image = var.finance_image, port = 8001 }
    scheduling = { image = var.scheduling_image, port = 8002 }
    mcp        = { image = var.mcp_image, port = 8003 }
  }
}

resource "aws_ecs_task_definition" "atlas" {
  for_each                 = local.task_defs
  family                   = "${local.name}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.exec.name
  task_role_arn            = aws_iam_role.task.name
  container_definitions = jsonencode([{
    name         = each.key
    image        = each.value.image
    portMappings = [{ containerPort = each.value.port, protocol = "tcp" }]
    environment = concat(
      local.auth_environment,
      each.key == "finance" ? [{ name = "ATLAS_RISK_MODEL_URL", value = "http://atlas-risk:8000" }] : []
    )
    secrets = each.key == "risk" ? [] : [{
      name      = "ATLAS_DATABASE_URL"
      valueFrom = aws_secretsmanager_secret.database_url.arn
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.atlas.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = each.key
      }
    }
  }])
  tags = local.common_tags
}

resource "aws_ecs_service" "atlas" {
  for_each               = local.task_defs
  name                   = "${local.name}-${each.key}"
  cluster                = aws_ecs_cluster.atlas.id
  task_definition        = aws_ecs_task_definition.atlas[each.key].arn
  desired_count          = var.ecs_min_capacity
  launch_type            = "FARGATE"
  enable_execute_command = true
  network_configuration {
    subnets          = aws_subnet.atlas[*].id
    security_groups  = [aws_security_group.services.id]
    assign_public_ip = true
  }
  lifecycle {
    ignore_changes = [desired_count]
  }
  # Only the mcp service is fronted by the ALB in this minimal layout; the
  # others are reachable inside the VPC and via port-forwarding for debugging.
  dynamic "load_balancer" {
    for_each = each.key == "mcp" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.mcp.arn
      container_name   = "mcp"
      container_port   = 8003
    }

    resource "aws_appautoscaling_target" "atlas" {
      for_each           = local.task_defs
      max_capacity       = var.ecs_max_capacity
      min_capacity       = var.ecs_min_capacity
      resource_id        = "service/${aws_ecs_cluster.atlas.name}/${aws_ecs_service.atlas[each.key].name}"
      scalable_dimension = "ecs:service:DesiredCount"
      service_namespace  = "ecs"
    }

    resource "aws_appautoscaling_policy" "cpu" {
      for_each           = local.task_defs
      name               = "${local.name}-${each.key}-cpu"
      policy_type        = "TargetTrackingScaling"
      resource_id        = aws_appautoscaling_target.atlas[each.key].resource_id
      scalable_dimension = aws_appautoscaling_target.atlas[each.key].scalable_dimension
      service_namespace  = aws_appautoscaling_target.atlas[each.key].service_namespace

      target_tracking_scaling_policy_configuration {
        target_value       = 60
        scale_in_cooldown  = 180
        scale_out_cooldown = 60
        predefined_metric_specification {
          predefined_metric_type = "ECSServiceAverageCPUUtilization"
        }
      }
    }
  }
  depends_on = [aws_lb_listener.https]
  tags       = local.common_tags
}

# ------------------------------------------------------------------ load balancer
resource "aws_lb" "atlas" {
  name               = "${local.name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.lb.id]
  subnets            = aws_subnet.atlas[*].id
  tags               = local.common_tags
}

resource "aws_lb_target_group" "mcp" {
  name        = "${local.name}-mcp"
  port        = 8003
  protocol    = "HTTP"
  vpc_id      = aws_vpc.atlas.id
  target_type = "ip"
  health_check {
    path                = "/health"
    interval            = 30
    healthy_threshold   = 3
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.atlas.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mcp.arn
  }
}

# Path rule so /mcp* hits the MCP group; the default above forwards too, but
# the explicit rule documents the layout (finance/scheduling add their own).
resource "aws_lb_listener_rule" "mcp_path" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mcp.arn
  }
  condition {
    path_pattern { values = ["/mcp*"] }
  }
}

resource "aws_cloudwatch_log_group" "atlas" {
  name              = "/ecs/atlas"
  retention_in_days = 14
}

# ------------------------------------------------------------------ iam + bedrock
resource "aws_iam_role" "exec" {
  name = "${local.name}-ecs-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "exec_logs" {
  role       = aws_iam_role.exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "exec_database_secret" {
  name = "${local.name}-database-secret"
  role = aws_iam_role.exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = aws_secretsmanager_secret.database_url.arn
    }]
  })
}

resource "aws_iam_role" "task" {
  name = "${local.name}-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

# Bedrock: allow the orchestrator service to invoke the Nova model only.
resource "aws_iam_role_policy" "task_bedrock" {
  name = "${local.name}-bedrock"
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = "arn:aws:bedrock:${var.region}::foundation-model/${var.bedrock_model}"
    }]
  })
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.atlas.id
}

output "cognito_app_client_id" {
  value = aws_cognito_user_pool_client.atlas.id
}

output "cognito_issuer" {
  value = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.atlas.id}"
}

output "cognito_hosted_ui_domain" {
  value = "https://${var.cognito_domain_prefix}.auth.${var.region}.amazoncognito.com"
}