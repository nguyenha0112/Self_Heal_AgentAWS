module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.30"

  vpc_id                   = var.vpc_id
  subnet_ids               = var.subnet_ids
  control_plane_subnet_ids = var.subnet_ids

  # Required for IRSA (IAM Roles for Service Accounts)
  enable_irsa = true

  # Cho phép truy cập API từ ngoài VPC (laptop chạy terraform/helm/kubectl).
  # Mặc định module ra private-only → provider helm/kubectl từ local bị i/o timeout.
  # Sandbox: mở 0.0.0.0/0; production nên giới hạn về IP văn phòng/VPN.
  cluster_endpoint_public_access       = true
  cluster_endpoint_private_access      = true
  cluster_endpoint_public_access_cidrs = ["0.0.0.0/0"]

  cluster_addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni    = { most_recent = true }
  }

  eks_managed_node_groups = {
    default_node_group = {
      min_size     = 2
      max_size     = 5
      desired_size = 2

      instance_types = ["t3.medium"]
      capacity_type  = "ON_DEMAND"
    }
  }

  tags = {
    Project     = "tf3-cdo-02"
    Environment = "dev"
  }
}
