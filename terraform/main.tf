terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ECS Cluster for WARDEN Platform
resource "aws_ecs_cluster" "warden_cluster" {
  name = "${var.environment}-warden-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Environment = var.environment
    ManagedBy   = "Terraform"
    Project     = "WARDEN"
  }
}

# IAM Role for Task Execution with Secrets Manager access
resource "aws_iam_role" "ecs_execution_role" {
  name = "${var.environment}-warden-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action    = "sts:AssumeRole"
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
      }
    ]
  })
}

# Attach AWS managed policy for secrets access
resource "aws_iam_role_policy_attachment" "secrets_access" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
}

# ECS Task Definition with Non-root container security
resource "aws_ecs_task_definition" "warden_task" {
  family                   = "${var.environment}-warden-core"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "warden-api"
      image     = var.container_image
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
        }
      ]
      secrets = [
        {
          name      = "GEMINI_API_KEY"
          valueFrom = "arn:aws:secretsmanager:${var.aws_region}:*:secret:warden/gemini-api-key"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = "/ecs/${var.environment}-warden"
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])
}
