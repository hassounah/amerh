# Terraform: Secrets Manager JSON Consolidation Gotcha

**Extracted:** 2026-02-09
**Context:** Consolidating multiple Secrets Manager secrets into one JSON secret to save costs

## Problem
When consolidating Secrets Manager secrets into a single JSON secret, the `arn:secret-name:json-key::` format (used to extract individual JSON keys) **only works in ECS task definition `secrets` blocks**. It does NOT work with:
- `aws_secretsmanager_secret_version` data sources (`secret_id` parameter)
- Any other Terraform resource that expects a plain secret ARN

If the RDS module reads the DB password via a data source like:
```hcl
data "aws_secretsmanager_secret_version" "db_password" {
  secret_id = var.db_password_secret_arn  # Fails with "arn:...:db_password::"
}
```
...it will break because the data source can't parse the JSON key path suffix.

## Solution
Keep secrets that are consumed by non-ECS resources (like RDS) as standalone secrets. Only consolidate secrets that are exclusively consumed by ECS task definitions.

```hcl
# DB password: always standalone (RDS reads it via data source)
resource "aws_secretsmanager_secret" "db_password" {
  name = "${var.project}/${var.env}/db-password"
  # No count - always created
}

# App secrets: consolidated into 1 JSON secret (only ECS consumes these)
resource "aws_secretsmanager_secret" "combined" {
  count = var.use_consolidated_secret ? 1 : 0
  name  = "${var.project}/${var.env}/app-secrets"
}

# Output for ECS: includes JSON key path
output "propelauth_api_key_secret_arn" {
  value = "${aws_secretsmanager_secret.combined[0].arn}:propelauth_api_key::"
}

# Output for RDS: plain ARN, no JSON key path
output "db_password_secret_arn" {
  value = aws_secretsmanager_secret.db_password.arn
}
```

## When to Use
Any time you consolidate Secrets Manager secrets into JSON format. Always audit all consumers of each secret ARN output to check whether they support the `arn:...:json-key::` format.
