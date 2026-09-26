terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "intelgraph"
      Environment = "lab"
      Purpose     = "adversary-emulation-range"
      ManagedBy   = "terraform"
    }
  }
}
