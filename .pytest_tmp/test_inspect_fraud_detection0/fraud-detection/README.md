# Fraud Detection Agent

Scans financial transactions in real time and flags anomalies.

## Tools

| Tool | Scope | Required |
|------|-------|----------|
| `scan_transaction` | read | yes |
| `flag_transaction` | write | yes |
| `alert_compliance_team` | write | no |

## Usage

```bash
agent pack examples/fraud-detection
agent validate fraud-detection-0.1.0.agent
```
