module "vpc" {
  source       = "../../modules/vpc"
  environment  = var.environment
  cluster_name = var.cluster_name
}

module "eks" {
  source       = "../../modules/eks"
  cluster_name = var.cluster_name
  vpc_id       = module.vpc.vpc_id
  subnet_ids   = module.vpc.private_subnets
}

module "observability" {
  source       = "../../modules/observability"
  cluster_name = module.eks.cluster_name
}
