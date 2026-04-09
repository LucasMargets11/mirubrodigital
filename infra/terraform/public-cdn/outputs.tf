# ═══════════════════════════════════════════════════════════════════════════════
# Public CDN & Distribution — Outputs
# ═══════════════════════════════════════════════════════════════════════════════
#
# These outputs are for go-live validation and monitoring setup.

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.public.id
}

output "cloudfront_domain_name" {
  description = "CloudFront domain name (d111xxx.cloudfront.net)"
  value       = aws_cloudfront_distribution.public.domain_name
}

output "s3_assets_bucket_arn" {
  description = "S3 bucket ARN for public assets"
  value       = aws_s3_bucket.assets.arn
}

output "s3_assets_bucket_name" {
  description = "S3 bucket name for public assets (for CI/CD sync)"
  value       = aws_s3_bucket.assets.id
}

output "waf_public_web_acl_arn" {
  description = "WAF WebACL ARN (CLOUDFRONT scope)"
  value       = aws_wafv2_web_acl.public.arn
}
