---
layout: post
title: "IAM Role Hygiene: Finding and Cleaning Up Unused Roles"
date: 2025-06-02
categories: aws security iam
tags: aws iam security cleanup least-privilege governance
---

# IAM Role Hygiene: Finding and Cleaning Up Unused Roles

IAM roles accumulate like browser tabs — you create them with good intentions, and before you know it there are hundreds and you're not sure which ones are actually doing anything. I recently tackled a cleanup across our AWS accounts and the results were eye-opening.

## The Scale of the Problem

In a typical AWS account that's been active for a few years, you'll find:

- Roles created for experiments that never went anywhere
- Roles from CloudFormation stacks that were deleted but the role wasn't
- Service-linked roles you didn't know existed
- Roles with overly permissive policies attached "temporarily"
- Duplicate roles doing the same thing

Each unused role is a potential attack surface. If it has broad permissions and someone compromises it, you've got a problem.

## Step 1: Identify Unused Roles

AWS provides the `RoleLastUsed` field, which tells you when a role was last used to make an API call. This is your primary signal:

```bash
#!/bin/bash
# Find roles not used in the last 90 days

DAYS=90
CUTOFF=$(date -d "-${DAYS} days" +%Y-%m-%dT%H:%M:%S 2>/dev/null || \
         date -v-${DAYS}d +%Y-%m-%dT%H:%M:%S)

echo "Roles not used since: $CUTOFF"
echo "---"

aws iam list-roles --query 'Roles[*].[RoleName,RoleLastUsed.LastUsedDate,CreateDate]' --output text | \
while IFS=$'\t' read -r name last_used created; do
  if [ "$last_used" = "None" ]; then
    echo "NEVER USED: $name (created: $created)"
  elif [[ "$last_used" < "$CUTOFF" ]]; then
    echo "STALE ($last_used): $name"
  fi
done
```

## Step 2: Categorize What You Find

Not all unused roles should be deleted. Categorize them:

### Safe to Delete
- Roles from deleted CloudFormation stacks
- Roles with names like `test-*`, `temp-*`, `experiment-*`
- Roles that have never been used and are older than 90 days

### Investigate First
- Roles used by scheduled jobs (they might run quarterly)
- Roles used by disaster recovery processes (rarely invoked but critical)
- Roles referenced in IaC that hasn't been deployed yet

### Don't Touch
- Service-linked roles (AWS manages these)
- Roles used by active services even if `RoleLastUsed` seems stale
- Break-glass / emergency access roles

## Step 3: Analyze Role Permissions

Before deleting, understand what each role can do. This helps prioritize — overly permissive unused roles are the highest risk:

```bash
#!/bin/bash
# List roles with their attached policies and inline policy count

aws iam list-roles --query 'Roles[*].RoleName' --output text | tr '\t' '\n' | \
while read -r role; do
  attached=$(aws iam list-attached-role-policies \
    --role-name "$role" \
    --query 'AttachedPolicies[*].PolicyName' \
    --output text)

  inline_count=$(aws iam list-role-policies \
    --role-name "$role" \
    --query 'length(PolicyNames)')

  # Flag roles with admin or wildcard access
  has_admin=false
  if echo "$attached" | grep -qi "admin\|fullaccess"; then
    has_admin=true
  fi

  echo "$role | attached: $attached | inline: $inline_count | admin: $has_admin"
done
```

## Step 4: Generate Access Advisor Data

IAM Access Advisor shows which services a role has actually accessed. This is more granular than `RoleLastUsed`:

```bash
# Generate service last accessed details
JOB_ID=$(aws iam generate-service-last-accessed-details \
  --arn arn:aws:iam::123456789012:role/my-role \
  --query 'JobId' --output text)

# Wait for the job to complete, then retrieve results
sleep 5
aws iam get-service-last-accessed-details \
  --job-id "$JOB_ID" \
  --query 'ServicesLastAccessed[?LastAuthenticated!=`null`].[ServiceName,LastAuthenticated]' \
  --output table
```

This tells you exactly which AWS services the role has been used with. A role might have S3, EC2, and Lambda permissions but only ever accessed S3 — that's a candidate for policy tightening.

## Step 5: Safe Deletion Process

Don't just delete roles. Follow this process:

1. **Detach all policies first** — this effectively disables the role without deleting it
2. **Wait 2 weeks** — if nothing breaks, proceed
3. **Delete inline policies**
4. **Remove from instance profiles**
5. **Delete the role**

```bash
#!/bin/bash
# Safely delete an IAM role and all its dependencies

ROLE_NAME="$1"

if [ -z "$ROLE_NAME" ]; then
  echo "Usage: $0 <role-name>"
  exit 1
fi

echo "Cleaning up role: $ROLE_NAME"

# Detach managed policies
for policy_arn in $(aws iam list-attached-role-policies \
  --role-name "$ROLE_NAME" \
  --query 'AttachedPolicies[*].PolicyArn' --output text); do
  echo "  Detaching: $policy_arn"
  aws iam detach-role-policy --role-name "$ROLE_NAME" --policy-arn "$policy_arn"
done

# Delete inline policies
for policy_name in $(aws iam list-role-policies \
  --role-name "$ROLE_NAME" \
  --query 'PolicyNames[*]' --output text); do
  echo "  Deleting inline policy: $policy_name"
  aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name "$policy_name"
done

# Remove from instance profiles
for profile in $(aws iam list-instance-profiles-for-role \
  --role-name "$ROLE_NAME" \
  --query 'InstanceProfiles[*].InstanceProfileName' --output text); do
  echo "  Removing from instance profile: $profile"
  aws iam remove-role-from-instance-profile \
    --role-name "$ROLE_NAME" \
    --instance-profile-name "$profile"
done

# Delete the role
echo "  Deleting role..."
aws iam delete-role --role-name "$ROLE_NAME"
echo "Done."
```

## Automating Ongoing Hygiene

Set up a monthly report using a Lambda function:

```python
import boto3
from datetime import datetime, timezone, timedelta

iam = boto3.client('iam')
sns = boto3.client('sns')

def lambda_handler(event, context):
    threshold = datetime.now(timezone.utc) - timedelta(days=90)
    unused_roles = []

    paginator = iam.get_paginator('list_roles')
    for page in paginator.paginate():
        for role in page['Roles']:
            name = role['RoleName']

            # Skip service-linked roles
            if role['Path'].startswith('/aws-service-role/'):
                continue

            last_used = role.get('RoleLastUsed', {}).get('LastUsedDate')

            if last_used is None:
                age = (datetime.now(timezone.utc) - role['CreateDate']).days
                if age > 90:
                    unused_roles.append(f"NEVER USED ({age}d old): {name}")
            elif last_used < threshold:
                days_unused = (datetime.now(timezone.utc) - last_used).days
                unused_roles.append(f"UNUSED ({days_unused}d): {name}")

    if unused_roles:
        message = f"Found {len(unused_roles)} unused IAM roles:\n\n"
        message += "\n".join(unused_roles)

        sns.publish(
            TopicArn='arn:aws:sns:us-east-1:123456789012:iam-hygiene',
            Subject=f'IAM Role Hygiene Report - {len(unused_roles)} unused roles',
            Message=message
        )

    return {'unused_role_count': len(unused_roles)}
```

## Prevention: Naming Conventions and Tagging

Make future cleanups easier:

```
# Naming convention
{service}-{purpose}-{environment}-role
# Examples: lambda-image-processor-prod-role, ec2-web-server-staging-role

# Required tags
aws iam tag-role --role-name my-role --tags \
  Key=Owner,Value=ops-team \
  Key=Project,Value=image-pipeline \
  Key=Environment,Value=production \
  Key=ManagedBy,Value=terraform
```

If a role doesn't have an `Owner` tag, it's the first candidate for cleanup.

## Key Takeaways

- Run `RoleLastUsed` audits monthly
- Unused roles with broad permissions are your highest priority
- Disable before deleting — detach policies and wait
- Service-linked roles are AWS-managed; leave them alone
- Tag roles at creation time with owner and purpose
- Automate the reporting so it doesn't depend on someone remembering to check

The cleanup itself took about two days across our accounts. Setting up the automated monthly report took another hour. Now we catch role drift before it becomes a problem.

---

**References:**
- [IAM Access Advisor](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_access-advisor.html)
- [IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [AWS Well-Architected Security Pillar](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html)
