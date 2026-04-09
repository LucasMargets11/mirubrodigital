# ═══════════════════════════════════════════════════════════════════════════════
# S3 — Public Assets Bucket
# ═══════════════════════════════════════════════════════════════════════════════
#
# Static assets (logos, blog images, marketing assets) served via CloudFront.
# NOT for user-uploaded media or app-internal files — those go in a separate
# private bucket in a future layer.

resource "aws_s3_bucket" "assets" {
  bucket = "${local.prefix}-public-assets"

  tags = { Name = "${local.prefix}-public-assets" }
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "assets" {
  bucket = aws_s3_bucket.assets.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "assets" {
  bucket = aws_s3_bucket.assets.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── CloudFront Origin Access Control (OAC) ───────────────────────────────────

resource "aws_cloudfront_origin_access_control" "assets" {
  name                              = "${local.prefix}-assets-oac"
  description                       = "OAC for S3 public assets bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ── Bucket policy: allow CloudFront OAC reads only ───────────────────────────

resource "aws_s3_bucket_policy" "assets_cloudfront" {
  bucket = aws_s3_bucket.assets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontOAC"
        Effect    = "Allow"
        Principal = { Service = "cloudfront.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.assets.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.public.arn
          }
        }
      }
    ]
  })
}
