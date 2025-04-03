---layout: post
title: "Migrating from AWS CLB to ALB"
date: 2024-04-10
categories: aws migration terraform
---

## Overview

Migrating from an AWS Classic Load Balancer (CLB) to an Application Load Balancer (ALB) can improve performance, security, and cost efficiency. This guide outlines the steps required for the migration, provides Terraform examples, and includes a testing strategy to ensure a smooth transition.

---

## Steps to Migrate

### 1. Assess Your Current CLB Configuration
- Identify the listeners, target instances, and health check settings of your existing CLB.
- Document the security groups and any associated DNS records.

### 2. Plan Your ALB Configuration
- Determine the required listeners (HTTP/HTTPS).
- Define target groups and health check settings.
- Plan for path-based or host-based routing if needed.

### 3. Update Terraform Code
Below is an example of how to define an ALB in Terraform:

````terraform
# filepath: /path/to/terraform/main.tf
resource "aws_lb" "example" {
  name               = "example-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = ["sg-12345678"]
  subnets            = ["subnet-12345678", "subnet-87654321"]

  enable_deletion_protection = false
}

resource "aws_lb_target_group" "example" {
  name     = "example-target-group"
  port     = 80
  protocol = "HTTP"
  vpc_id   = "vpc-12345678"

  health_check {
    path                = "/"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.example.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "forward"
    target_group_arn = aws_lb_target_group.example.arn
  }
}
````

### 4. Migrate Traffic
- Update DNS records to point to the ALB's DNS name.
- Gradually shift traffic from the CLB to the ALB to monitor performance and stability.

---

## Testing Strategy

1. **Pre-Migration Testing**
   - Verify the ALB configuration using tools like `curl` or Postman.
   - Ensure health checks are passing for all target instances.

2. **Canary Testing**
   - Route a small percentage of traffic to the ALB and monitor for errors or latency issues.

3. **Full Traffic Cutover**
   - Once confident, update DNS records to fully route traffic to the ALB.
   - Monitor metrics in AWS CloudWatch for anomalies.

4. **Post-Migration Validation**
   - Confirm that all application functionality works as expected.
   - Decommission the CLB after a stabilization period.

---

## Conclusion

Migrating from a CLB to an ALB can provide significant benefits, but careful planning and testing are essential. Use the provided Terraform examples and testing strategy to ensure a seamless transition.
