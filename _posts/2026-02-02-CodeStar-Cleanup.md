---
layout: post
title: "AWS CodeStar & Legacy DevOps Pipeline Cleanup"
date: 2026-02-02
categories: aws devops cicd
tags: aws codestar codepipeline devops migration cleanup
---

# AWS CodeStar & Legacy DevOps Pipeline Cleanup

If you've been on AWS long enough, you've probably accumulated some CodeStar projects, old CodePipeline configurations, and maybe even some CodeCommit repos that nobody has pushed to in years. AWS deprecated CodeStar in 2024, and while existing projects still work, it's a good time to audit your CI/CD landscape and clean house.

## Taking Inventory

First, figure out what you have:

```bash
# List CodeStar projects
aws codestar list-projects \
  --query 'projects[*].[id,name]' \
  --output table

# List CodePipeline pipelines
aws codepipeline list-pipelines \
  --query 'pipelines[*].[name,created,updated]' \
  --output table

# List CodeCommit repositories
aws codecommit list-repositories \
  --query 'repositories[*].[repositoryName,lastModifiedDate]' \
  --output table

# List CodeBuild projects
aws codebuild list-projects
```

For each pipeline, check if it's actually been used recently:

```bash
# Check last execution for each pipeline
for pipeline in $(aws codepipeline list-pipelines --query 'pipelines[*].name' --output text); do
  last_exec=$(aws codepipeline list-pipeline-executions \
    --pipeline-name "$pipeline" \
    --max-items 1 \
    --query 'pipelineExecutionSummaries[0].[status,startTime]' \
    --output text 2>/dev/null)
  echo "$pipeline: $last_exec"
done
```

## Identifying What to Keep vs. Remove

### Keep
- Pipelines that have executed in the last 90 days
- Pipelines referenced in active infrastructure (Terraform, CloudFormation)
- CodeCommit repos that are actively used (check last push date)

### Migrate
- CodeStar projects that are still active — migrate to standalone CodePipeline or GitHub Actions
- Pipelines using deprecated features or old runtimes

### Remove
- CodeStar projects for experiments that ended months ago
- Pipelines that haven't run in 6+ months
- CodeCommit repos with no commits in the last year
- CodeBuild projects with no recent builds

## Migrating from CodeStar

CodeStar created a bundle of resources — a CodeCommit repo, CodeBuild project, CodePipeline, and often an Elastic Beanstalk or Lambda deployment. To migrate:

### Step 1: Document What CodeStar Created

```bash
PROJECT_ID="my-codestar-project"

# List all resources in the project
aws codestar describe-project --id "$PROJECT_ID"

# Get the CloudFormation stack
aws cloudformation describe-stacks \
  --stack-name "awscodestar-${PROJECT_ID}" \
  --query 'Stacks[0].Outputs' \
  --output table
```

### Step 2: Extract the Pipeline Configuration

```bash
# Get the pipeline definition
aws codepipeline get-pipeline \
  --name "awscodestar-${PROJECT_ID}-Pipeline" \
  --query 'pipeline' > pipeline-definition.json
```

### Step 3: Recreate Without CodeStar

If you're moving to GitHub Actions (which I'd recommend for most teams):

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS
on:
  push:
    branches: [main]

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/GitHubActionsRole
          aws-region: us-east-1

      - name: Build
        run: |
          npm ci
          npm run build

      - name: Deploy
        run: |
          aws s3 sync build/ s3://my-app-bucket/
          # or: aws lambda update-function-code ...
          # or: aws ecs update-service ...
```

If you're staying with CodePipeline, create a standalone pipeline without the CodeStar wrapper:

```bash
aws codepipeline create-pipeline \
  --pipeline file://pipeline-definition.json
```

## Cleaning Up CodeStar Projects

CodeStar projects are backed by CloudFormation stacks. Deleting the project deletes the stack and all its resources:

```bash
# WARNING: This deletes everything in the project
aws codestar delete-project \
  --id "$PROJECT_ID" \
  --delete-stack
```

If you want to keep some resources (like the CodeCommit repo), remove them from the CloudFormation stack first:

```bash
# Update the stack to retain the repo
aws cloudformation update-stack \
  --stack-name "awscodestar-${PROJECT_ID}" \
  --template-body file://updated-template.json \
  --parameters ParameterKey=ProjectId,ParameterValue="$PROJECT_ID"
```

## Cleaning Up Unused Pipelines

```bash
#!/bin/bash
# Delete pipelines that haven't run in 180 days

DAYS=180
CUTOFF=$(date -d "-${DAYS} days" +%Y-%m-%dT%H:%M:%S)

for pipeline in $(aws codepipeline list-pipelines --query 'pipelines[*].name' --output text); do
  last_start=$(aws codepipeline list-pipeline-executions \
    --pipeline-name "$pipeline" \
    --max-items 1 \
    --query 'pipelineExecutionSummaries[0].startTime' \
    --output text 2>/dev/null)

  if [ "$last_start" = "None" ] || [ -z "$last_start" ] || [[ "$last_start" < "$CUTOFF" ]]; then
    echo "STALE: $pipeline (last run: $last_start)"
    # Uncomment to delete:
    # aws codepipeline delete-pipeline --name "$pipeline"
  fi
done
```

## Cleaning Up CodeCommit Repos

```bash
# Find repos with no recent activity
for repo in $(aws codecommit list-repositories --query 'repositories[*].repositoryName' --output text); do
  last_modified=$(aws codecommit get-repository \
    --repository-name "$repo" \
    --query 'repositoryMetadata.lastModifiedDate' \
    --output text)
  echo "$repo: last modified $last_modified"
done
```

Before deleting a CodeCommit repo, make sure the code exists elsewhere:

```bash
# Clone the repo first as a backup
git clone codecommit::us-east-1://my-old-repo backup-my-old-repo

# Then delete
aws codecommit delete-repository --repository-name my-old-repo
```

## Cleaning Up CodeBuild Projects

```bash
# Find CodeBuild projects with no recent builds
for project in $(aws codebuild list-projects --query 'projects[*]' --output text); do
  last_build=$(aws codebuild list-builds-for-project \
    --project-name "$project" \
    --query 'ids[0]' \
    --output text 2>/dev/null)

  if [ "$last_build" = "None" ] || [ -z "$last_build" ]; then
    echo "NO BUILDS: $project"
  else
    build_time=$(aws codebuild batch-get-builds \
      --ids "$last_build" \
      --query 'builds[0].startTime' \
      --output text)
    echo "$project: last build $build_time"
  fi
done
```

## IAM Cleanup

Don't forget the IAM roles that CodeStar and CodePipeline created:

```bash
# Find CodeStar-related roles
aws iam list-roles \
  --query 'Roles[?contains(RoleName, `CodeStar`) || contains(RoleName, `codepipeline`) || contains(RoleName, `codebuild`)].[RoleName,RoleLastUsed.LastUsedDate]' \
  --output table
```

Cross-reference with the roles that are still in use by active pipelines before deleting.

## Tips

- Always take inventory before deleting anything
- Clone CodeCommit repos before removing them, even if you think the code is elsewhere
- Check CloudFormation for resources that might be orphaned after CodeStar deletion
- Update any documentation or runbooks that reference old pipeline names
- If migrating to GitHub Actions, use OIDC federation instead of long-lived access keys
- Keep a log of what you deleted and when — your future self will thank you

The cleanup took about a day across our accounts and removed a surprising amount of clutter. More importantly, it gave us a clear picture of our actual CI/CD landscape instead of a mix of active and abandoned pipelines.

---

**References:**
- [AWS CodeStar Deprecation Notice](https://docs.aws.amazon.com/codestar/latest/userguide/welcome.html)
- [CodePipeline Documentation](https://docs.aws.amazon.com/codepipeline/latest/userguide/welcome.html)
- [GitHub Actions with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
