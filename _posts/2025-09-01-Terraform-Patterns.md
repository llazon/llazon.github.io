---
layout: post
title: "Terraform Patterns for AWS at Scale"
date: 2025-09-01
categories: aws infrastructure terraform
tags: aws terraform iac multi-account modules state-management
---

# Terraform Patterns for AWS at Scale

I've been using Terraform to manage AWS infrastructure for years now, and the patterns that work for a single account with a handful of resources fall apart fast when you're managing dozens of accounts with hundreds of resources. Here are the patterns that have held up as we've scaled.

## Project Structure

The single-directory-with-everything approach doesn't scale. Here's the structure I've landed on:

```
terraform/
├── modules/
│   ├── vpc/
│   ├── ecs-cluster/
│   ├── rds/
│   ├── monitoring/
│   └── security-baseline/
├── environments/
│   ├── production/
│   │   ├── us-east-1/
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── terraform.tfvars
│   │   └── us-west-2/
│   ├── staging/
│   └── development/
├── accounts/
│   ├── security/
│   ├── logging/
│   └── shared-services/
└── global/
    ├── iam/
    ├── organizations/
    └── route53/
```

Key principles:
- Modules are reusable building blocks with no environment-specific config
- Each environment/region combo is a separate state file
- Account-level resources (IAM, Organizations) are managed separately
- Global resources (Route53, IAM) have their own directory

## Module Design

Good modules are opinionated but flexible. Here's what a well-structured VPC module looks like:

```hcl
# modules/vpc/variables.tf
variable "name" {
  type        = string
  description = "Name prefix for all VPC resources"
}

variable "cidr" {
  type        = string
  description = "VPC CIDR block"
}

variable "azs" {
  type        = list(string)
  description = "Availability zones"
}

variable "private_subnets" {
  type        = list(string)
  description = "Private subnet CIDR blocks"
}

variable "public_subnets" {
  type        = list(string)
  description = "Public subnet CIDR blocks"
  default     = []
}

variable "enable_nat_gateway" {
  type        = bool
  default     = true
}

variable "single_nat_gateway" {
  type        = bool
  default     = false
  description = "Use a single NAT gateway (cost savings for non-prod)"
}

variable "enable_vpc_endpoints" {
  type        = bool
  default     = true
  description = "Create S3 and DynamoDB gateway endpoints"
}

variable "tags" {
  type        = map(string)
  default     = {}
}
```

```hcl
# modules/vpc/main.tf
resource "aws_vpc" "this" {
  cidr_block           = var.cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = var.name
  })
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnets)
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.private_subnets[count.index]
  availability_zone = var.azs[count.index]

  tags = merge(var.tags, {
    Name = "${var.name}-private-${var.azs[count.index]}"
    Tier = "private"
  })
}

# Gateway endpoints (free)
resource "aws_vpc_endpoint" "s3" {
  count        = var.enable_vpc_endpoints ? 1 : 0
  vpc_id       = aws_vpc.this.id
  service_name = "com.amazonaws.${data.aws_region.current.name}.s3"
  route_table_ids = [aws_route_table.private.id]
}

resource "aws_vpc_endpoint" "dynamodb" {
  count        = var.enable_vpc_endpoints ? 1 : 0
  vpc_id       = aws_vpc.this.id
  service_name = "com.amazonaws.${data.aws_region.current.name}.dynamodb"
  route_table_ids = [aws_route_table.private.id]
}

data "aws_region" "current" {}
```

```hcl
# modules/vpc/outputs.tf
output "vpc_id" {
  value = aws_vpc.this.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}
```

## State Management

Remote state in S3 with DynamoDB locking is the standard, but the details matter:

```hcl
# environments/production/us-east-1/backend.tf
terraform {
  backend "s3" {
    bucket         = "myorg-terraform-state"
    key            = "production/us-east-1/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

State file organization rules:
- One state file per environment per region
- Never put more than ~200 resources in a single state file
- If `terraform plan` takes more than 30 seconds, it's time to split
- Use `terraform_remote_state` data sources sparingly — they create tight coupling

### State File Bootstrap

The chicken-and-egg problem: you need an S3 bucket for state, but you want to manage that bucket with Terraform. Here's my approach:

```bash
#!/bin/bash
# bootstrap.sh - Run once to create state infrastructure

BUCKET="myorg-terraform-state"
TABLE="terraform-locks"
REGION="us-east-1"

aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$REGION"

aws s3api put-bucket-versioning \
  --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "$BUCKET" \
  --server-side-encryption-configuration '{
    "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]
  }'

aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws dynamodb create-table \
  --table-name "$TABLE" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION"
```

## Multi-Account Patterns

### Provider Aliases for Cross-Account

```hcl
provider "aws" {
  region = "us-east-1"
  alias  = "security"

  assume_role {
    role_arn = "arn:aws:iam::222222222222:role/TerraformRole"
  }
}

# Use the aliased provider for resources in the security account
resource "aws_guardduty_detector" "security" {
  provider = aws.security
  enable   = true
}
```

### Shared Data Between Accounts

Use SSM Parameter Store or Terraform remote state for sharing values:

```hcl
# In the networking account
resource "aws_ssm_parameter" "vpc_id" {
  name  = "/shared/networking/vpc-id"
  type  = "String"
  value = module.vpc.vpc_id
}

# In the application account
data "aws_ssm_parameter" "vpc_id" {
  provider = aws.networking
  name     = "/shared/networking/vpc-id"
}
```

## Variable Management

### Use tfvars Files Per Environment

```hcl
# environments/production/us-east-1/terraform.tfvars
environment    = "production"
vpc_cidr       = "10.0.0.0/16"
instance_type  = "m5.xlarge"
min_capacity   = 3
max_capacity   = 10
enable_waf     = true
```

```hcl
# environments/development/us-east-1/terraform.tfvars
environment    = "development"
vpc_cidr       = "10.100.0.0/16"
instance_type  = "t3.medium"
min_capacity   = 1
max_capacity   = 2
enable_waf     = false
```

### Validation

Add validation to catch mistakes early:

```hcl
variable "environment" {
  type = string
  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "Environment must be production, staging, or development."
  }
}

variable "vpc_cidr" {
  type = string
  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "Must be a valid CIDR block."
  }
}
```

## Tagging Strategy

Enforce consistent tagging with a `default_tags` block:

```hcl
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Environment = var.environment
      ManagedBy   = "terraform"
      Project     = var.project
      Owner       = var.team
      CostCenter  = var.cost_center
    }
  }
}
```

## CI/CD for Terraform

{% raw %}
```yaml
# .github/workflows/terraform.yml
name: Terraform
on:
  pull_request:
    paths: ['environments/**', 'modules/**']
  push:
    branches: [main]
    paths: ['environments/**', 'modules/**']

jobs:
  plan:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    strategy:
      matrix:
        environment: [production, staging]
        region: [us-east-1]
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - name: Terraform Plan
        working-directory: environments/${{ matrix.environment }}/${{ matrix.region }}
        run: |
          terraform init
          terraform plan -no-color -out=tfplan
        env:
          AWS_ROLE_ARN: ${{ secrets[format('{0}_ROLE_ARN', matrix.environment)] }}

  apply:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    needs: [plan]
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - name: Terraform Apply
        working-directory: environments/production/us-east-1
        run: |
          terraform init
          terraform apply -auto-approve
```
{% endraw %}

## Patterns to Avoid

- **Workspaces for environments** — they share state config and make it too easy to apply to the wrong environment
- **Massive monolithic state files** — split by service or component
- **Hardcoded values in modules** — everything should be a variable
- **`terraform apply` from laptops** — always use CI/CD for production
- **Ignoring `terraform plan` output** — read every line before approving

Terraform at scale is less about the HCL and more about the patterns around it — state management, module design, CI/CD, and team conventions. Get those right and the infrastructure code almost writes itself.

---

**References:**
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform Best Practices](https://www.terraform-best-practices.com/)
- [AWS Multi-Account Strategy](https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/organizing-your-aws-environment.html)
