---
layout: post
title: "Building AWS Lambda Functions in Rust"
date: 2025-03-03
categories: aws serverless rust
tags: aws lambda rust serverless cargo-lambda performance
---

# Building AWS Lambda Functions in Rust

I've been writing Lambda functions in Python and Node.js for years, and they're great for most use cases. But when I needed to process millions of S3 objects with tight latency requirements, I reached for Rust — and the results were worth the learning curve.

## Why Rust on Lambda?

The numbers speak for themselves:

- Cold starts under 20ms (compared to 200-500ms for Python/Node, seconds for Java)
- Memory usage as low as 128MB for non-trivial workloads
- Execution speed that lets you do more within the same billing window
- No runtime overhead — Rust compiles to a native binary

The tradeoff is development speed. Rust takes longer to write, but for Lambda functions that run millions of times, the per-invocation savings add up fast.

## Getting Started with cargo-lambda

The `cargo-lambda` tool is the easiest way to build and deploy Rust Lambda functions. It handles cross-compilation, packaging, and deployment.

```bash
# Install cargo-lambda
pip3 install cargo-lambda

# Or with Homebrew
brew tap cargo-lambda/cargo-lambda
brew install cargo-lambda

# Create a new Lambda project
cargo lambda new my-function
```

This generates a project with the right dependencies already configured:

```toml
# Cargo.toml
[package]
name = "my-function"
version = "0.1.0"
edition = "2021"

[dependencies]
lambda_runtime = "0.11"
serde = { version = "1", features = ["derive"] }
tokio = { version = "1", features = ["macros"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
```

## A Real Example: Processing S3 Events

Here's a Lambda function that responds to S3 events — the kind of thing I use for processing uploaded files:

```rust
use aws_sdk_s3::Client as S3Client;
use lambda_runtime::{service_fn, Error, LambdaEvent};
use serde::{Deserialize, Serialize};
use tracing::info;

#[derive(Deserialize)]
struct S3Event {
    #[serde(rename = "Records")]
    records: Vec<S3EventRecord>,
}

#[derive(Deserialize)]
struct S3EventRecord {
    s3: S3Entity,
}

#[derive(Deserialize)]
struct S3Entity {
    bucket: S3Bucket,
    object: S3Object,
}

#[derive(Deserialize)]
struct S3Bucket {
    name: String,
}

#[derive(Deserialize)]
struct S3Object {
    key: String,
    size: Option<i64>,
}

#[derive(Serialize)]
struct Response {
    processed: usize,
    status: String,
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .json()
        .init();

    let config = aws_config::load_defaults(aws_config::BehaviorVersion::latest()).await;
    let s3_client = S3Client::new(&config);

    lambda_runtime::run(service_fn(|event: LambdaEvent<S3Event>| {
        handler(&s3_client, event)
    }))
    .await
}

async fn handler(
    s3_client: &S3Client,
    event: LambdaEvent<S3Event>,
) -> Result<Response, Error> {
    let mut processed = 0;

    for record in &event.payload.records {
        let bucket = &record.s3.bucket.name;
        let key = &record.s3.object.key;

        info!(bucket = %bucket, key = %key, "Processing object");

        // Get the object
        let obj = s3_client
            .get_object()
            .bucket(bucket)
            .key(key)
            .send()
            .await?;

        let body = obj.body.collect().await?.into_bytes();
        info!(size = body.len(), "Retrieved object");

        // Do your processing here
        // ...

        processed += 1;
    }

    Ok(Response {
        processed,
        status: "success".to_string(),
    })
}
```

## Building and Deploying

```bash
# Build for Lambda (cross-compiles to Amazon Linux 2)
cargo lambda build --release

# Test locally
cargo lambda watch
# In another terminal:
cargo lambda invoke --data-file test-event.json

# Deploy directly
cargo lambda deploy my-function \
  --iam-role arn:aws:iam::123456789012:role/lambda-execution-role
```

The `cargo lambda build --release` command handles cross-compilation to the `x86_64-unknown-linux-gnu` target (or `aarch64` if you specify `--arm64`). The resulting binary is small and fast.

## ARM64 vs x86_64

Lambda supports both architectures. ARM64 (Graviton2) is 20% cheaper and in my testing, Rust performs comparably on both. Use ARM64 unless you have a specific reason not to:

```bash
cargo lambda build --release --arm64
cargo lambda deploy my-function --iam-role $ROLE_ARN
```

Make sure your function is configured for `arm64` in the Lambda console or your IaC.

## Error Handling Patterns

Rust's type system makes error handling explicit, which is actually a huge advantage for Lambda functions. Here's a pattern I use:

```rust
use thiserror::Error;

#[derive(Error, Debug)]
enum ProcessingError {
    #[error("S3 error: {0}")]
    S3(#[from] aws_sdk_s3::Error),

    #[error("Invalid input: {0}")]
    InvalidInput(String),

    #[error("Processing failed for key {key}: {reason}")]
    ProcessingFailed { key: String, reason: String },
}

// In your handler, errors are explicit and typed
async fn process_object(
    client: &S3Client,
    bucket: &str,
    key: &str,
) -> Result<(), ProcessingError> {
    if key.is_empty() {
        return Err(ProcessingError::InvalidInput(
            "Object key cannot be empty".to_string(),
        ));
    }

    let result = client
        .get_object()
        .bucket(bucket)
        .key(key)
        .send()
        .await
        .map_err(|e| ProcessingError::ProcessingFailed {
            key: key.to_string(),
            reason: e.to_string(),
        })?;

    // Process...
    Ok(())
}
```

## Cold Start Performance

I ran some benchmarks comparing cold starts across runtimes for a function that initializes an S3 client and processes a single object:

| Runtime | Cold Start | Warm Invocation | Memory |
|---------|-----------|-----------------|--------|
| Rust (ARM64) | ~12ms | ~3ms | 128MB |
| Python 3.12 | ~250ms | ~45ms | 128MB |
| Node.js 20 | ~180ms | ~15ms | 128MB |
| Java 21 (SnapStart) | ~150ms | ~8ms | 512MB |

Rust's cold start advantage is dramatic. For event-driven workloads where functions scale to zero frequently, this matters a lot.

## Structured Logging

Use `tracing` with JSON output for CloudWatch-friendly structured logs:

```rust
use tracing::{info, warn, instrument};

#[instrument(skip(s3_client))]
async fn handler(
    s3_client: &S3Client,
    event: LambdaEvent<S3Event>,
) -> Result<Response, Error> {
    info!(
        record_count = event.payload.records.len(),
        "Processing S3 event"
    );

    // tracing automatically captures function parameters
    // and creates spans for distributed tracing
    Ok(Response { /* ... */ })
}
```

## Tips From Building Rust Lambdas

- Start with `cargo-lambda` — don't try to set up cross-compilation manually
- Use `--release` builds always; debug builds are significantly slower
- The AWS SDK for Rust is production-ready and well-documented
- Keep your function focused — Rust's compile times mean you want small, single-purpose functions
- Use `tokio` for async I/O; it's what the Lambda runtime is built on
- Test locally with `cargo lambda watch` before deploying — the feedback loop is much faster
- ARM64 is the sweet spot for cost/performance

Rust on Lambda isn't for every use case. For a simple API Gateway handler that queries DynamoDB, Python is probably fine. But for high-throughput data processing, image manipulation, or anything where cold starts matter — Rust is hard to beat.

---

**References:**
- [AWS Lambda Rust Runtime](https://github.com/awslabs/aws-lambda-rust-runtime)
- [cargo-lambda](https://www.cargo-lambda.info/)
- [AWS SDK for Rust](https://docs.aws.amazon.com/sdk-for-rust/latest/dg/welcome.html)
- [Lambda Pricing](https://aws.amazon.com/lambda/pricing/)
