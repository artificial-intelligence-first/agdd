---
title: Security Policy
last_synced: 2025-10-24
description: Security considerations, vulnerability reporting, and production deployment guidelines
change_log:
  - 2025-10-24: Added front-matter and rate limiting production recommendations
  - 2025-10-24: Added production deployment checklist and rate limiting defaults
---

# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability within the MAGSAG framework, please report it responsibly:

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead, please use one of the following methods:

### Option 1: GitHub Private Vulnerability Reporting (Recommended)

Use GitHub's private vulnerability reporting feature:
1. Go to the [Security tab](https://github.com/artificial-intelligence-first/magsag/security/advisories/new) of this repository
2. Click "Report a vulnerability"
3. Fill in the details of the vulnerability

### Option 2: GitHub Security Advisories

If private reporting is not available, you can report through:
- **GitHub Discussions**: Create a private security discussion thread
- **Repository Issues**: Contact repository maintainers to request a private disclosure channel

Include the following in your report:
- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact and severity assessment
- Any suggested fixes (if available)

We will acknowledge your report within 48 hours and provide a detailed response indicating the next steps in handling your report. After the initial reply, we will keep you informed of the progress toward a fix and full announcement.

## Supported Versions

We provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: (latest minor version only) |
| < 0.1.0 | :x:                |

We recommend always using the latest release to ensure you have the most recent security patches.

## Security Considerations

When deploying the MAGSAG framework, please be aware of the following security considerations:

### API Key Authentication

- **Development:** API key authentication is optional for local development
- **Production:** API key authentication is **strongly recommended** for production deployments
- Configure via `MAGSAG_API_KEY` environment variable
- Use strong, randomly-generated keys (minimum 32 characters)
- Rotate keys periodically and whenever team membership changes

### GitHub Webhook Security

- **Mandatory:** GitHub webhook secret verification is **required** for all webhook integrations
- Configure via `MAGSAG_GITHUB_WEBHOOK_SECRET` environment variable
- Use a strong, randomly-generated secret (minimum 32 characters)
- Never commit secrets to version control
- Verify webhook signatures before processing events

### Transport Security

- **Production:** Always use HTTPS in production environments
- Use TLS 1.2 or higher
- Ensure valid SSL/TLS certificates
- Consider placing the API behind a reverse proxy (nginx, Caddy) for additional security layers

### Rate Limiting

- **Production Recommended:** Enable rate limiting to prevent abuse
- **Default:** Rate limiting is **disabled** (`MAGSAG_RATE_LIMIT_QPS=None`)
- **To Enable:** Set `MAGSAG_RATE_LIMIT_QPS` environment variable (e.g., `10` for 10 queries per second)
- For distributed deployments, use Redis-backed rate limiting via `MAGSAG_REDIS_URL`
- Monitor rate limit violations and adjust as needed

**Example:**
```bash
# Enable rate limiting at 10 QPS
export MAGSAG_RATE_LIMIT_QPS=10

# For distributed deployments
export MAGSAG_REDIS_URL=redis://localhost:6379
```

### Data Security

- Agent execution artifacts are stored in `.runs/` directory
- Ensure appropriate filesystem permissions
- Consider encryption at rest for sensitive data
- Implement backup and retention policies
- Use the storage layer's vacuum feature to clean up old data

### Dependency Security

- Regularly update dependencies using `uv sync`
- Monitor security advisories for dependencies
- Review `pyproject.toml` for any pinned vulnerable versions
- Run `uv sync --upgrade` periodically to get security patches

## Production Deployment Checklist

Before deploying MAGSAG to production, ensure the following security measures are in place:

### Required Environment Variables

- [ ] **`MAGSAG_API_KEY`**: Set a strong API key (generate with `openssl rand -hex 32`)
- [ ] **`MAGSAG_CORS_ORIGINS`**: Configure with your actual frontend/client domains (no wildcard `["*"]`)
- [ ] **`MAGSAG_API_DEBUG`**: Set to `false` (disable debug mode and hot reload)

### Recommended Environment Variables

- [ ] **`MAGSAG_RATE_LIMIT_QPS`**: Enable rate limiting (recommended: `10`)
- [ ] **`MAGSAG_REDIS_URL`**: Configure Redis for distributed rate limiting in multi-instance deployments
- [ ] **`MAGSAG_GITHUB_WEBHOOK_SECRET`**: Set if using GitHub webhooks (generate with `openssl rand -hex 32`)
- [ ] **`MAGSAG_OTEL_TRACING_ENABLED`**: Enable observability for production monitoring
- [ ] **`MAGSAG_OTLP_ENDPOINT`**: Configure OpenTelemetry collector endpoint

### Infrastructure Requirements

- [ ] **HTTPS/TLS**: Deploy behind HTTPS with valid SSL/TLS certificates (TLS 1.2+)
- [ ] **Reverse Proxy**: Use nginx, Caddy, or similar for additional security layers
- [ ] **Firewall Rules**: Restrict API access to known client IPs/networks
- [ ] **Filesystem Permissions**: Ensure `.runs/` directory has appropriate permissions (read/write for API user only)

### Rate Limiting Behavior

**Default (in-memory)**:
- Rate limiting state is stored in process memory
- Suitable for single-process deployments
- Resets on application restart

**Redis-backed (distributed)**:
- Rate limiting state is shared across all API instances
- Suitable for multi-process/multi-instance deployments
- **Fail-open behavior**: If Redis connection fails, rate limiting falls back to in-memory mode
  - Logs warning: `"Redis unavailable, using in-memory rate limiter"`
  - Application continues to operate with degraded rate limiting
  - Reconnects automatically when Redis becomes available

**Configuration Example**:
```bash
# Single-instance deployment (in-memory)
export MAGSAG_RATE_LIMIT_QPS=10

# Multi-instance deployment (Redis-backed)
export MAGSAG_RATE_LIMIT_QPS=10
export MAGSAG_REDIS_URL=redis://localhost:6379
```

### Secret Management

- [ ] Never commit `.env` files or secrets to version control
- [ ] Use environment-specific secret management (AWS Secrets Manager, Vault, etc.)
- [ ] Rotate API keys and webhook secrets periodically (at least quarterly)
- [ ] Use different secrets for development, staging, and production

### Monitoring and Logging

- [ ] Enable OpenTelemetry tracing for distributed request tracking
- [ ] Configure log aggregation (ELK, Datadog, etc.)
- [ ] Set up alerts for rate limit violations, authentication failures, and errors
- [ ] Monitor `.runs/` directory disk usage and implement retention policies

### Deployment Validation

After deployment, verify:

- [ ] Authentication is enforced (test with missing/invalid API key)
- [ ] Rate limiting is active (test with burst requests)
- [ ] CORS is correctly configured (test from browser client)
- [ ] HTTPS is enforced (no HTTP fallback)
- [ ] Webhook signature verification is working (if using GitHub integration)
- [ ] Observability data is flowing to monitoring systems

## Security Best Practices

1. **Minimal Permissions:** Run the API server with minimal necessary permissions
2. **Network Isolation:** Use firewalls and network policies to restrict access
3. **Logging and Monitoring:** Enable comprehensive logging and monitor for suspicious activity
4. **Secret Management:** Use environment variables or secret management systems (never hardcode)
5. **Input Validation:** All agent payloads are validated against JSON schemas
6. **Regular Updates:** Keep the framework and dependencies up to date

## Known Security Limitations

- The framework stores execution artifacts on the filesystem without encryption by default
- Rate limiting is **disabled by default** and must be explicitly enabled via `MAGSAG_RATE_LIMIT_QPS`
  - When enabled, token bucket rate limiting is in-memory by default
  - Use Redis (`MAGSAG_REDIS_URL`) for distributed deployments
- No built-in user authentication/authorization (relies on optional API key authentication)

## Disclosure Policy

When we receive a security report, we will:

1. Confirm the vulnerability and determine its impact
2. Develop and test a fix
3. Prepare a security advisory
4. Release a patched version
5. Publish the security advisory with credit to the reporter (if desired)

We aim to handle all security reports within 30 days of initial disclosure.

## Contact

For security-related questions or concerns:
- Use the vulnerability reporting methods described above
- Or open a GitHub Discussion for security-related questions (non-vulnerability)

For general support and non-security issues, please use GitHub Issues.
