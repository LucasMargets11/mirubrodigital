# ═══════════════════════════════════════════════════════════════════════════════
# Public DNS & Certificates — Outputs
# ═══════════════════════════════════════════════════════════════════════════════
#
# Consumed by:
#   public/cdn  — terraform_remote_state "dns" (zone_id, acm_certificate_arn)
#   core/alb.tf — acm_certificate_arn (paste manually when uncommenting HTTPS)

# ── Route 53 ─────────────────────────────────────────────────────────────────

output "zone_id" {
  description = "Route 53 hosted zone ID for mirubro.com"
  value       = aws_route53_zone.main.zone_id
}

output "zone_name_servers" {
  description = "Name servers to configure in Hostinger"
  value       = aws_route53_zone.main.name_servers
}

# ── ACM Certificate ──────────────────────────────────────────────────────────

output "acm_certificate_arn" {
  description = "ACM certificate ARN (mirubro.com + www + api) — us-east-1"
  value       = aws_acm_certificate.main.arn
}

output "acm_certificate_status" {
  description = "ACM certificate validation status (ISSUED when ready)"
  value       = aws_acm_certificate_validation.main.certificate_arn != "" ? "ISSUED" : "PENDING"
}

# ── DNS Records ──────────────────────────────────────────────────────────────

output "api_fqdn" {
  description = "FQDN for the API subdomain (api.mirubro.com)"
  value       = aws_route53_record.api.fqdn
}
