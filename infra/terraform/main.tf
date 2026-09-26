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
      [{ name = "ATLAS_DATABASE_URL", value = "postgresql+psycopg2://${var.db_user}:${var.db_password}@${aws_db_instance.atlas.endpoint}/atlas" }],
      each.key == "finance" ? [{ name = "RISK_MODEL_URL", value = "http://atlas-risk:8000" }] : [],
      each.key == "mcp" ? [{ name = "ATLAS_REQUIRE_AUTH", value = "1" }] : []
    )
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
  desired_count          = 1
  launch_type            = "FARGATE"
  enable_execute_command = true
  network_configuration {
    subnets          = aws_subnet.atlas[*].id
    security_groups  = [aws_security_group.services.id]
    assign_public_ip = true
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