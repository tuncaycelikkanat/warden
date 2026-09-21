variable "aws_region" {
  type        = string
  description = "AWS deployment region"
  default     = "eu-central-1"
}

variable "environment" {
  type        = string
  description = "Deployment environment (prod, staging, dev)"
  default     = "prod"
}

variable "container_image" {
  type        = string
  description = "Docker image repository URI and tag"
  default     = "warden-platform:latest"
}

variable "task_cpu" {
  type        = string
  description = "CPU units allocated for ECS Fargate task"
  default     = "1024"
}

variable "task_memory" {
  type        = string
  description = "Memory (MB) allocated for ECS Fargate task"
  default     = "2048"
}
