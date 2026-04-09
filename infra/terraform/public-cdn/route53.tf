# ═══════════════════════════════════════════════════════════════════════════════
# Route 53 Records — www + apex → CloudFront
# ═══════════════════════════════════════════════════════════════════════════════
#
# Both records are A-type aliases to the CloudFront distribution.
# The CloudFront Function handles apex → www 301 redirect at the edge.

resource "aws_route53_record" "www" {
  zone_id = local.dns.zone_id
  name    = local.fqdn_www
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.public.domain_name
    zone_id                = aws_cloudfront_distribution.public.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "apex" {
  zone_id = local.dns.zone_id
  name    = local.fqdn_apex
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.public.domain_name
    zone_id                = aws_cloudfront_distribution.public.hosted_zone_id
    evaluate_target_health = false
  }
}
